"""Bounded sensitivity grid over private native Freqtrade 2026.9 backtests.

Every populated cell comes from a separate official backtest.  No interpolation,
slippage-as-fill, Hyperopt seed, paper action, or engine modification is implied.
"""
import hashlib
import json
import math
import re
import shutil
import signal
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server import api_optimization as opt
from freqtrade.rpc.api_server.api_optimization import (
    optimization_lock, child_environment, normalize_cli_numbers, verified_inputs,
    stop_owned_group,
)
from freqtrade.rpc.api_server.api_presets import inspect_parameters, load_preset, validate_values
from freqtrade.rpc.api_server.api_local_strategies import root as strategy_root
from freqtrade.rpc.api_server.api_runs import digest, freeze, run_root
from freqtrade.rpc.api_server.api_studio import Manifest, json_safe, storage, write_check
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG

router = APIRouter()
MAX_CELLS = 30
MAX_INPUT_BYTES = 3 * 1024 ** 3
ACTIVE = {'prepared', 'running', 'cancelling'}
_lock = threading.RLock()
_active_id: str | None = None
_owned: dict[str, subprocess.Popen] = {}


def now():
    return datetime.now(timezone.utc).isoformat()


def root(config):
    folder = storage(config) / 'sensitivity'
    folder.mkdir(exist_ok=True)
    if folder.is_symlink(): raise HTTPException(409, 'Kho quét độ nhạy không hợp lệ.')
    return folder


def path_for(uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid): raise HTTPException(422, 'Mã thí nghiệm không hợp lệ.')
    p = root(config) / uid
    if p.is_symlink() or (p / 'record.json').is_symlink() or not (p / 'record.json').is_file():
        raise HTTPException(404, 'Không có thí nghiệm này.')
    return p


class Axis(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str
    step: float = Field(gt=0)
    radius: int = Field(default=1, ge=1, le=2)


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: str
    revision: str
    preset_id: str | None = None
    settings: dict
    axes: list[Axis] = Field(min_length=1, max_length=2)
    fee_scenarios: list[float] = Field(default_factory=list, max_length=3)


def _values(field, base, axis):
    if field['param_type'] not in ('IntParameter', 'RealParameter', 'DecimalParameter') or not field['load']:
        raise HTTPException(422, 'Chỉ quét tham số số mà engine cho phép nạp: ' + axis.name)
    if not math.isfinite(axis.step) or axis.step <= 0:
        raise HTTPException(422, 'Bước quét phải hữu hạn và lớn hơn 0.')
    if field['param_type'] == 'IntParameter' and (axis.step != int(axis.step) or type(base) is not int):
        raise HTTPException(422, 'Tham số nguyên cần bước nguyên.')
    if field['param_type'] == 'DecimalParameter':
        tick = Decimal(1).scaleb(-field['decimals'])
        if Decimal(str(axis.step)) != Decimal(str(axis.step)).quantize(tick):
            raise HTTPException(422, 'Bước quét vượt độ chính xác của tham số.')
    base_decimal, step_decimal = Decimal(str(base)), Decimal(str(axis.step))
    result = []
    for offset in range(-axis.radius, axis.radius + 1):
        value = base_decimal + step_decimal * offset
        if Decimal(str(field['low'])) <= value <= Decimal(str(field['high'])):
            item = int(value) if field['param_type'] == 'IntParameter' else float(value)
            if item not in result: result.append(item)
    if len(result) < 2 or base not in result:
        raise HTTPException(422, 'Không có đủ giá trị lân cận trong phạm vi native: ' + axis.name)
    return result


def _source_hashes(config):
    source_root = strategy_root(config)
    found = {}
    for file in source_root.rglob('*.py'):
        if '__pycache__' in file.parts: continue
        if file.is_symlink() or not file.resolve().is_relative_to(source_root):
            raise HTTPException(422, 'Không quét với helper liên kết ngoài thư viện.')
        found['inputs/strategies/' + file.relative_to(source_root).as_posix()] = digest(file)
    return found


def plan(req, config):
    from freqtrade.configuration import TimeRange
    from freqtrade.rpc.api_server.api_schemas import BacktestRequest
    allowed = {'timerange', 'timeframe', 'timeframe_detail', 'dry_run_wallet',
               'max_open_trades', 'stake_amount', 'enable_protections'}
    if any(key not in allowed for key in req.settings):
        raise HTTPException(422, 'Tham số backtest không được hỗ trợ.')
    raw = req.settings.get('timerange')
    if not isinstance(raw, str) or not re.fullmatch(r'\d{8}-\d{8}', raw):
        raise HTTPException(422, 'Chọn khoảng UTC đóng trước khi quét độ nhạy.')
    try:
        bounds = TimeRange.parse_timerange(raw)
        if not bounds.startts or not bounds.stopts or bounds.startts >= bounds.stopts:
            raise ValueError('Khoảng ngày không hợp lệ.')
        BacktestRequest(strategy=req.strategy, **req.settings, backtest_cache='none')
        normalize_cli_numbers({**config, **req.settings, 'strategy': req.strategy})
    except (ValueError, TypeError, ValidationError) as error:
        raise HTTPException(422, str(error)) from error
    source_hashes = _source_hashes(config)
    schema = inspect_parameters(req.strategy, config)
    if _source_hashes(config) != source_hashes:
        raise HTTPException(409, 'Helper đổi khi đọc định nghĩa tham số.')
    if schema['revision'] != req.revision:
        raise HTTPException(409, 'Mã đã đổi. Tải lại trước khi quét.')
    if len({axis.name for axis in req.axes}) != len(req.axes):
        raise HTTPException(422, 'Không chọn cùng một tham số hai lần.')
    baseline = {field['name']: field['value'] for field in schema['fields'] if field['load']}
    if req.preset_id:
        preset, _ = load_preset(req.strategy, req.preset_id, config)
        if (preset['revision'] != schema['revision'] or preset['schema_revision'] != schema['schema_revision']
                or preset['parameter_revision'] != schema['parameter_revision']):
            raise HTTPException(409, 'Bộ tham số khác mã hoặc JSON hiện tại.')
        baseline = preset['values']
    validate_values(baseline, schema['fields'])
    fields = {field['name']: field for field in schema['fields']}
    axes = []
    for axis in req.axes:
        field = fields.get(axis.name)
        if field is None: raise HTTPException(422, 'Không tìm thấy tham số: ' + axis.name)
        axes.append({'name': axis.name, 'space': field['space'], 'base': baseline[axis.name],
                     'values': _values(field, baseline[axis.name], axis),
                     'step': axis.step, 'radius': axis.radius})
    fee = config.get('fee')
    if type(fee) not in (int, float) or not math.isfinite(fee) or fee < 0 or fee > .01:
        raise HTTPException(422, 'Phí gốc phải rõ ràng và nằm trong [0, 1%].')
    scenarios = req.fee_scenarios or [fee]
    if (any(type(x) not in (int, float) or not math.isfinite(x) or x < 0 or x > .01 for x in scenarios)
            or len(set(scenarios)) != len(scenarios) or fee not in scenarios):
        raise HTTPException(422, 'Kịch bản phí phải hữu hạn, không trùng, gồm cả phí gốc.')
    from itertools import product
    cells = []
    for combination in product(*(axis['values'] for axis in axes)):
        parameters = dict(zip((axis['name'] for axis in axes), combination))
        values = {**baseline, **parameters}
        validate_values(values, schema['fields'])
        for scenario in scenarios:
            cells.append({'index': len(cells), 'parameters': parameters, 'fee': scenario,
                          'status': 'pending', 'result': None, 'error': None})
    if len(cells) > MAX_CELLS:
        raise HTTPException(422, f'Quá {MAX_CELLS} ô native; giảm số bước hoặc kịch bản phí.')
    return {'strategy': req.strategy, 'revision': req.revision, 'schema': schema,
            'baseline': baseline, 'axes': axes, 'fee_scenarios': scenarios,
            'cells': cells, 'estimated_backtests': len(cells), 'max_cells': MAX_CELLS,
            '_source_hashes': source_hashes,
            'note': 'Mỗi ô sẽ là một backtest native độc lập. Ô chưa chạy có result=null. Fee là kịch bản native; không cộng slippage giả định.'}


@router.post('/sensitivity/preview')
def preview(req: SensitivityRequest, config=Depends(get_config)):
    planned = plan(req, config)
    planned.pop('_source_hashes')
    base = Path(config['datadir']).resolve()
    estimated = sum(p.stat().st_size for p in base.rglob('*.feather') if p.is_file() and not p.is_symlink())
    return json_safe({**planned, 'estimated_input_bytes': estimated})


def _identity(pid):
    return opt.process_identity(pid)


def _orphan_alive(record):
    identity, command = record.get('active_process_identity'), record.get('active_command')
    if not identity or not command or identity != _identity(identity['pid']): return False
    try:
        actual = (Path('/proc') / str(identity['pid']) / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        return actual == command
    except (OSError, UnicodeError): return True


def guard_sensitivity_orphans(config):
    for file in root(config).glob('*/record.json'):
        if file.is_symlink() or file.parent.is_symlink(): continue
        record = json.loads(file.read_text())
        if (record['status'] in ACTIVE or record.get('orphan_process_alive')) and _orphan_alive(record):
            raise HTTPException(409, 'Tiến trình quét độ nhạy cũ còn sống. Chờ nó kết thúc.')


def _ensure_idle(config):
    if _active_id is not None: raise HTTPException(409, 'Quét độ nhạy đang chạy.')
    opt.ensure_idle(config)
    from freqtrade.rpc.api_server.api_walk_forward import guard_wfa_orphans
    guard_wfa_orphans(config)
    guard_sensitivity_orphans(config)


def _persist(p, record):
    write_check(p / 'record.json', record)


def _refreshed(p):
    record = json.loads((p / 'record.json').read_text())
    if record['status'] in ACTIVE and record['id'] != _active_id:
        record.update(status='interrupted', finished_at=now(),
                      orphan_process_alive=_orphan_alive(record),
                      error='Dịch vụ khởi động lại; ô chưa chạy không tự tiếp tục.')
        _persist(p, record)
    elif record['status'] == 'interrupted' and record.get('orphan_process_alive') and not _orphan_alive(record):
        record['orphan_process_alive'] = False
        _persist(p, record)
    return json_safe(record)


def _reserve(uid):
    global _active_id
    _active_id = uid
    opt._active_id = 'sensitivity:' + uid
    ApiBG.analysis_running = True


def _release(uid):
    global _active_id
    _owned.pop(uid, None)
    if _active_id == uid:
        _active_id = None
        if opt._active_id == 'sensitivity:' + uid: opt._active_id = None
        ApiBG.analysis_running = False


@router.post('/sensitivity')
def start(req: SensitivityRequest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with opt.optimization_lock, _lock:
        _ensure_idle(config)
        planned = plan(req, config)
        p, base = freeze(Manifest(strategy=req.strategy, revision=req.revision,
                                  settings=req.settings, preset_id=req.preset_id), config)
        destination = root(config) / base['id']
        p.rename(destination)
        p = destination
        frozen = json.loads((p / 'inputs.json').read_text())
        expected_param = planned['schema']['parameter_revision']
        current_param = frozen['files'].get('inputs/strategies/' + req.strategy + '.json', 'none')
        captured_sources = {name: value for name, value in frozen['files'].items()
                            if name.startswith('inputs/strategies/') and name.endswith('.py')}
        if captured_sources != planned['_source_hashes'] or (not req.preset_id and current_param != expected_param):
            base.update(status='failed', error='Mã/helper/tham số đổi khi chuẩn bị snapshot.', finished_at=now())
            _persist(p, base)
            raise HTTPException(409, base['error'])
        if base['input_bytes'] > MAX_INPUT_BYTES:
            base.update(status='failed', error='Snapshot lớn hơn ngân sách 3 GiB.', finished_at=now())
            _persist(p, base)
            raise HTTPException(422, base['error'])
        record = {k: base[k] for k in ('id', 'strategy', 'revision', 'engine', 'created_at', 'settings',
                                        'input_manifest_sha256', 'input_files', 'input_bytes')}
        record.update(status='prepared', axes=planned['axes'], fee_scenarios=planned['fee_scenarios'],
                      baseline=planned['baseline'], schema=planned['schema'], cells=planned['cells'],
                      preset=base.get('preset'), completed_cells=0, estimated_backtests=len(planned['cells']),
                      current_cell=None, active_process_identity=None, active_command=None,
                      cancel_requested_at=None, error=None,
                      note='Mỗi ô là native backtest riêng. Không tính slippage hậu xử lý là fill.')
        _persist(p, record)
        _reserve(record['id'])
        background_tasks.add_task(_run, p)
        return json_safe(record)


def _sync_cancel(p, record):
    saved = json.loads((p / 'record.json').read_text())
    if saved.get('cancel_requested_at'):
        record['cancel_requested_at'] = saved['cancel_requested_at']
        record['status'] = 'cancelling'


def _copy_strategies(p, cell, frozen):
    rootdir = cell / 'inputs/strategies'
    rootdir.mkdir(parents=True)
    for name, expected in frozen['files'].items():
        if not name.startswith('inputs/strategies/') or not name.endswith(('.py', '.json')):
            continue
        relative = Path(name).relative_to('inputs/strategies')
        if '..' in relative.parts: raise ValueError('Đường dẫn chiến lược không hợp lệ.')
        target = rootdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p / name, target)
        if digest(target) != expected: raise ValueError('Mã/tham số nguồn đã đổi: ' + name)


def _parameter_file(p, record, cell):
    parameter = p / 'cells' / str(cell['index']) / 'inputs/strategies' / (record['strategy'] + '.json')
    if parameter.is_file():
        params = json.loads(parameter.read_text(encoding='utf-8-sig'))
        if params.get('strategy_name') != record['strategy'] or not isinstance(params.get('params'), dict):
            raise ValueError('JSON tham số native không đúng chiến lược.')
    else:
        params = {'strategy_name': record['strategy'], 'ft_stratparam_v': 1, 'params': {}}
    values = {**record['baseline'], **cell['parameters']}
    grouped = validate_values(values, record['schema']['fields'])
    for group, members in grouped.items():
        params['params'].setdefault(group, {}).update(members)
    parameter.write_text(json.dumps(params, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return digest(parameter)


def _runtime(p, cell, frozen):
    target = p / 'cells' / str(cell['index'])
    runtime = deepcopy(frozen['config'])
    runtime.update(fee=cell['fee'], dry_run=True, backtest_cache='none',
                   user_data_dir=str(target / 'inputs'), datadir=str(p / 'inputs/data'),
                   strategy_path=str(target / 'inputs/strategies'), recursive_strategy_search=False)
    normalize_cli_numbers(runtime)
    file = target / 'runtime.json'
    file.write_text(json.dumps(runtime, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    return file


def _command(p, cell, record):
    target = p / 'cells' / str(cell['index'])
    return [sys.executable, '-m', 'freqtrade', 'backtesting', '--config', str(target / 'runtime.json'),
            '--userdir', str(target / 'inputs'), '--strategy-path', str(target / 'inputs/strategies'),
            '--datadir', str(p / 'inputs/data'), '--strategy', record['strategy'],
            '--timerange', record['settings']['timerange'], '--export', 'trades',
            '--backtest-directory', str(target / 'output'), '--cache', 'none', '--no-color']


def _summary(p, cell, record, parameter_sha, runtime_sha):
    target = p / 'cells' / str(cell['index'])
    if digest(target / 'runtime.json') != runtime_sha:
        raise ValueError('Cấu hình ô đã đổi sau khi chạy.')
    if digest(target / 'inputs/strategies' / (record['strategy'] + '.json')) != parameter_sha:
        raise ValueError('Tham số ô đã đổi sau khi chạy.')
    archives = list((target / 'output').glob('*.zip'))
    if len(archives) != 1 or archives[0].is_symlink(): raise ValueError('Native chưa xuất đúng một ZIP.')
    archive = archives[0]
    with ZipFile(archive) as bundle:
        embedded = bundle.read(archive.stem + '_' + record['strategy'] + '.py')
        if hashlib.sha256(embedded).hexdigest() != record['revision']:
            raise ValueError('Mã trong kết quả native khác snapshot.')
        params = bundle.read(archive.stem + '_' + record['strategy'] + '.json')
        if hashlib.sha256(params).hexdigest() != parameter_sha:
            raise ValueError('Tham số trong kết quả native khác ô đã chạy.')
        stats = json.loads(bundle.read(archive.stem + '.json'))['strategy'][record['strategy']]
    keys = ('total_trades', 'profit_total_abs', 'profit_total', 'max_drawdown_account',
            'profit_factor', 'wins', 'losses', 'backtest_start', 'backtest_end',
            'timeframe', 'total_volume', 'fee_total')
    return json_safe({'artifact': archive.relative_to(p).as_posix(), 'artifact_sha256': digest(archive),
                      'parameter_sha256': parameter_sha, 'runtime_sha256': runtime_sha,
                      'summary': {key: stats.get(key) for key in keys},
                      'note': 'Backtest native riêng cho ô; mức phí trong runtime, không ước lượng slippage.'})


def _run(p):
    uid = p.name
    record = json.loads((p / 'record.json').read_text())
    try:
        frozen = verified_inputs(p, record)
        record['status'] = 'running'
        _persist(p, record)
        for cell in record['cells']:
            with optimization_lock, _lock:
                _sync_cancel(p, record)
                if record.get('cancel_requested_at'): break
                record['current_cell'] = cell['index']
                cell['status'] = 'running'
                _persist(p, record)
            verified_inputs(p, record)
            target = p / 'cells' / str(cell['index'])
            (target / 'inputs').mkdir(parents=True)
            (target / 'output').mkdir()
            _copy_strategies(p, target, frozen)
            parameter_sha = _parameter_file(p, record, cell)
            runtime_sha = digest(_runtime(p, cell, frozen))
            command = _command(p, cell, record)
            with optimization_lock, _lock:
                _sync_cancel(p, record)
                if record.get('cancel_requested_at'):
                    cell['status'] = 'cancelled'
                    _persist(p, record)
                    break
                record['active_command'] = command
                _persist(p, record)
                try:
                    with (p / 'native.log').open('ab') as log:
                        process = subprocess.Popen(command, cwd=target, env=child_environment(),
                                                   stdin=subprocess.DEVNULL, stdout=log,
                                                   stderr=subprocess.STDOUT, start_new_session=True)
                except Exception:
                    record['active_command'] = None
                    _persist(p, record)
                    raise
                _owned[uid] = process
                try:
                    record['active_process_identity'] = _identity(process.pid)
                    _persist(p, record)
                except Exception:
                    stop_owned_group(process, signal.SIGINT)
                    opt.complete_cancel(process)
                    _owned.pop(uid, None)
                    raise
            process.wait()
            with optimization_lock, _lock:
                _sync_cancel(p, record)
                _owned.pop(uid, None)
                record['active_process_identity'] = None
                record['active_command'] = None
                _persist(p, record)
            if record.get('cancel_requested_at'):
                cell['status'] = 'cancelled'
                _persist(p, record)
                break
            if process.returncode != 0:
                cell.update(status='failed', error='Native backtest kết thúc với lỗi; xem log thí nghiệm.')
                record['completed_cells'] += 1
                _persist(p, record)
                break
            try:
                verified_inputs(p, record)
                cell['result'] = _summary(p, cell, record, parameter_sha, runtime_sha)
                cell['status'] = 'success'
            except Exception as error:
                cell.update(status='failed', error=str(error))
                record['completed_cells'] += 1
                _persist(p, record)
                break
            record['completed_cells'] += 1
            _persist(p, record)
        _sync_cancel(p, record)
        record.update(status='cancelled' if record.get('cancel_requested_at') else
                      'failed' if any(c['status'] == 'failed' for c in record['cells']) else 'success',
                      finished_at=now(), current_cell=None)
        _persist(p, record)
    except Exception as error:
        if record.get('current_cell') is not None:
            current = record['cells'][record['current_cell']]
            if current['status'] == 'running': current.update(status='failed', error=str(error))
        record.update(status='failed', error=str(error), finished_at=now(), current_cell=None)
        _persist(p, record)
    finally:
        with optimization_lock, _lock:
            _release(uid)


@router.get('/sensitivity')
def list_sensitivity(strategy: str | None = None, config=Depends(get_config)):
    with _lock:
        records = []
        for file in sorted(root(config).glob('*/record.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            if file.is_symlink() or file.parent.is_symlink(): continue
            item = _refreshed(file.parent)
            if strategy is None or item.get('strategy') == strategy: records.append(item)
            if len(records) >= 100: break
        return {'jobs': records}


@router.get('/sensitivity/{uid}')
def get_sensitivity(uid: str, config=Depends(get_config)):
    with _lock: return _refreshed(path_for(uid, config))


@router.post('/sensitivity/{uid}/cancel')
def cancel(uid: str, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock, _lock:
        p = path_for(uid, config)
        record = _refreshed(p)
        if record['status'] not in ACTIVE: return record
        if uid != _active_id:
            raise HTTPException(409, 'Không còn quyền sở hữu child; chưa gửi tín hiệu dừng.')
        record.update(status='cancelling', cancel_requested_at=record.get('cancel_requested_at') or now())
        _persist(p, record)
        process = _owned.get(uid)
        if process is not None:
            stop_owned_group(process, signal.SIGINT)
            background_tasks.add_task(opt.complete_cancel, process)
        return json_safe(record)
