"""Independent BTC/ETH × timeframe experiments with the pinned native engine.

Each cell owns a frozen research snapshot and a separate simulated wallet.  The
results are deliberately never aggregated into a shared-capital portfolio.
"""

import ast
import json
import re
import signal
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import read, target
from freqtrade.rpc.api_server.api_studio import Manifest, json_safe, storage, write_check
from freqtrade.rpc.api_server.api_runs import digest, freeze
from freqtrade.rpc.api_server import api_optimization as opt
from freqtrade.rpc.api_server.api_optimization import optimization_lock, normalize_cli_numbers
from freqtrade.rpc.api_server.api_walk_forward import _native_summary
from freqtrade.rpc.api_server.api_data_quality import (
    _ALLOWED_PAIRS, _ALLOWED_FRAMES, _frame_seconds, data_source_lock,
    guard_research, quality_report,
)
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG


router = APIRouter()
ACTIVE = {'prepared', 'running', 'cancelling'}
MAX_CELLS = 6
MAX_INPUT_BYTES = 6 * 1024 ** 3
_lock = threading.RLock()
_owned: dict[str, subprocess.Popen] = {}
_active_id: str | None = None


def now():
    return datetime.now(timezone.utc).isoformat()


def root(config):
    directory = storage(config) / 'matrices'
    directory.mkdir(exist_ok=True)
    return directory


def path_for(uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(422, 'Mã ma trận không hợp lệ.')
    path = root(config) / uid
    if path.is_symlink() or (path / 'record.json').is_symlink() or not (path / 'record.json').is_file():
        raise HTTPException(404, 'Không có ma trận này.')
    return path


class MatrixRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: str
    revision: str
    preset_id: str | None = None
    settings: dict
    pairs: list[str] = Field(min_length=1, max_length=2)
    timeframes: list[str] = Field(min_length=1, max_length=3)


def _validate(req, config):
    if len(req.pairs) != len(set(req.pairs)) or not set(req.pairs) <= _ALLOWED_PAIRS:
        raise HTTPException(422, 'Chỉ chọn BTC/ETH USDT-M Futures một lần mỗi cặp.')
    if len(req.timeframes) != len(set(req.timeframes)) or not set(req.timeframes) <= _ALLOWED_FRAMES:
        raise HTTPException(422, 'Khung thời gian trùng hoặc chưa hỗ trợ.')
    if len(req.pairs) * len(req.timeframes) > MAX_CELLS:
        raise HTTPException(422, 'Ma trận tối đa sáu ô.')
    configured = set(config.get('exchange', {}).get('pair_whitelist', []))
    if not set(req.pairs) <= configured:
        raise HTTPException(422, 'Cặp chưa nằm trong cấu hình nghiên cứu hiện tại.')
    if 'timeframe' in req.settings:
        raise HTTPException(422, 'Đưa khung thời gian vào timeframes, không đặt trong settings.')
    required = {'timerange', 'timeframe_detail', 'dry_run_wallet', 'stake_amount', 'max_open_trades'}
    if not required <= req.settings.keys():
        raise HTTPException(422, 'Cần khai báo ngày, khung chi tiết, vốn, stake và số lệnh tối đa.')
    detail = req.settings['timeframe_detail']
    _frame_seconds(detail)
    if any(_frame_seconds(detail) > _frame_seconds(frame) for frame in req.timeframes):
        raise HTTPException(422, 'Khung chi tiết phải nhỏ hơn hoặc bằng từng khung chính.')
    document = read(target(req.strategy, config))
    if document['revision'] != req.revision:
        raise HTTPException(409, 'Mã chiến lược đã đổi; tải lại trước khi xem ma trận.')
    tree = ast.parse(document['content'])
    strategy_class = next((node for node in tree.body
                           if isinstance(node, ast.ClassDef) and node.name == req.strategy), None)
    warmup = None
    if strategy_class:
        for node in strategy_class.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'startup_candle_count':
                try:
                    literal = ast.literal_eval(node.value)
                    warmup = literal if type(literal) is int else None
                except (ValueError, TypeError):
                    warmup = None
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == 'startup_candle_count' and node.value is not None:
                try:
                    literal = ast.literal_eval(node.value)
                    warmup = literal if type(literal) is int else None
                except (ValueError, TypeError):
                    warmup = None
    if warmup is None or not 0 <= warmup <= 10000:
        raise HTTPException(422, 'Cần startup_candle_count cố định trong chiến lược.')
    guard_research(config)
    return warmup


def _cell_config(config, pair):
    isolated = deepcopy(config)
    isolated['exchange'] = deepcopy(config['exchange'])
    isolated['exchange']['pair_whitelist'] = [pair]
    return isolated


def _cell_settings(req, frame):
    return {**req.settings, 'timeframe': frame}


def _preview(req, config):
    warmup = _validate(req, config)
    cells = []
    with data_source_lock:
        for pair in req.pairs:
            isolated = _cell_config(config, pair)
            for frame in req.timeframes:
                report = quality_report(isolated, req.settings['timerange'], frame,
                                        req.settings['timeframe_detail'], warmup,
                                        verify_funding=True, persist=False)
                cell = {'pair': pair, 'timeframe': frame, 'status': report['status'],
                        'issues': report['issues'], 'dataset_sha256': report['dataset_sha256'],
                        'files': [{k: row.get(k) for k in ('pair', 'timeframe', 'type', 'status', 'sha256', 'rows', 'required_start', 'required_end')}
                                  for row in report['files']],
                        'funding_verification': report['funding_verification']['status']}
                # The normal research manifest validates the full native API
                # recipe and the exact strategy revision for every ready cell.
                if cell['status'] == 'ok':
                    from freqtrade.rpc.api_server.api_studio import manifest
                    prepared = manifest(Manifest(strategy=req.strategy, revision=req.revision,
                                                 preset_id=req.preset_id,
                                                 settings=_cell_settings(req, frame)), isolated)
                    cell['preflight_id'] = prepared['id']
                cells.append(cell)
    data_bytes = sum(p.stat().st_size for p in Path(config['datadir']).resolve().rglob('*.feather')
                     if p.is_file() and not p.is_symlink())
    return {'ready': all(cell['status'] == 'ok' for cell in cells), 'cells': cells,
            'estimated_runs': len(cells), 'estimated_input_bytes': data_bytes * len(cells),
            'engine': 'Freqtrade 2026.9',
            'note': 'Mỗi ô là backtest native với vốn mô phỏng riêng. Không cộng lợi nhuận thành danh mục vốn chung. Funding phải đối chiếu Binance thành công trước khi chạy.'}


@router.post('/matrix/preview')
def preview(req: MatrixRequest, config=Depends(get_config)):
    return _preview(req, config)


def _persist(path, record):
    write_check(path / 'record.json', record)


def _identity(pid):
    return opt.process_identity(pid)


def _orphan_alive(record):
    identity, command = record.get('active_process_identity'), record.get('active_command')
    if not identity or not command or identity != _identity(identity['pid']):
        return False
    try:
        actual = (Path('/proc') / str(identity['pid']) / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        return actual == command
    except (OSError, UnicodeError):
        return True


def guard_matrix_orphans(config):
    for file in root(config).glob('*/record.json'):
        if file.is_symlink() or file.parent.is_symlink():
            continue
        record = json.loads(file.read_text())
        if (record['status'] in ACTIVE or record.get('orphan_process_alive')) and _orphan_alive(record):
            raise HTTPException(409, 'Tiến trình ma trận cũ vẫn chạy; chờ hoàn tất trước khi dùng engine.')


def _refreshed(path):
    record = json.loads((path / 'record.json').read_text())
    if record['status'] in ACTIVE and record['id'] != _active_id:
        record.update(status='interrupted', finished_at=now(), orphan_process_alive=_orphan_alive(record),
                      error='Dịch vụ khởi động lại; ma trận không tự chạy tiếp.')
        _persist(path, record)
    elif record['status'] == 'interrupted' and record.get('orphan_process_alive') and not _orphan_alive(record):
        record['orphan_process_alive'] = False
        _persist(path, record)
    return json_safe(record)


def _reserve(uid):
    global _active_id
    _active_id = uid
    opt._active_id = 'matrix:' + uid
    ApiBG.analysis_running = True


def _release(uid):
    global _active_id
    _owned.pop(uid, None)
    if _active_id == uid:
        _active_id = None
        if opt._active_id == 'matrix:' + uid:
            opt._active_id = None
        ApiBG.analysis_running = False


@router.post('/matrix')
def start(req: MatrixRequest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock, _lock:
        if _active_id is not None:
            raise HTTPException(409, 'Ma trận khác đang chạy.')
        opt.ensure_idle(config)
        guard_matrix_orphans(config)
        # Keep the audit generation and all cell snapshots in one data lock.
        # Otherwise a repair could replace one file after the remote funding
        # audit but before a later cell is frozen.
        with data_source_lock:
            result = _preview(req, config)
            if not result['ready']:
                raise HTTPException(422, 'Có ô thiếu dữ liệu, sai dữ liệu hoặc chưa xác minh funding. Xem trước để sửa từng ô.')
            if result['estimated_input_bytes'] > MAX_INPUT_BYTES:
                raise HTTPException(422, 'Bản sao ma trận dự kiến vượt 6 GiB; chọn ít ô hơn.')
            uid = uuid4().hex
            path = root(config) / uid
            (path / 'cells').mkdir(parents=True)
            cells = []
            total_bytes = 0
            try:
                for index, examined in enumerate(result['cells']):
                    isolated = _cell_config(config, examined['pair'])
                    settings = _cell_settings(req, examined['timeframe'])
                    temporary, frozen_record = freeze(Manifest(strategy=req.strategy, revision=req.revision,
                                                               preset_id=req.preset_id, settings=settings), isolated)
                    destination = path / 'cells' / str(index)
                    temporary.rename(destination)
                    total_bytes += frozen_record['input_bytes']
                    if total_bytes > MAX_INPUT_BYTES:
                        raise HTTPException(422, 'Bản sao ma trận vượt 6 GiB; chọn ít ô hơn.')
                    cells.append({'index': index, 'pair': examined['pair'], 'timeframe': examined['timeframe'],
                                  'status': 'pending', 'timerange': settings['timerange'],
                                  'wallet_usdt': settings['dry_run_wallet'], 'stake_amount': settings['stake_amount'],
                                  'input_manifest_sha256': frozen_record['input_manifest_sha256'],
                                  'input_bytes': frozen_record['input_bytes'],
                                  'dataset_sha256': examined['dataset_sha256'],
                                  'preflight_id': frozen_record['preflight_id'],
                                  'artifact': None, 'summary': None, 'error': None})
                record = {'id': uid, 'strategy': req.strategy, 'revision': req.revision,
                          'engine': 'Freqtrade 2026.9', 'status': 'prepared', 'created_at': now(),
                          'settings': req.settings, 'pairs': req.pairs, 'timeframes': req.timeframes,
                          'total_cells': len(cells), 'completed_cells': 0, 'cells': cells,
                          'input_bytes': total_bytes, 'current_cell': None, 'cancel_requested_at': None,
                          'active_process_identity': None, 'active_command': None,
                          'research_status': 'pending', 'orphan_process_alive': False, 'error': None,
                          'note': 'Các ô backtest độc lập; mỗi ô đặt lại vốn/vị thế. Không phải danh mục BTC+ETH dùng chung vốn.'}
                _persist(path, record)
            except Exception:
                # A preflight failure has not reserved the engine. Partial
                # private snapshots never become a valid job.
                raise
        _reserve(uid)
        background_tasks.add_task(_run, path)
        return json_safe(record)


def _sync_cancel(path, record):
    saved = json.loads((path / 'record.json').read_text())
    if saved.get('cancel_requested_at'):
        record['cancel_requested_at'] = saved['cancel_requested_at']
        record['status'] = 'cancelling'


def _runtime(path, frozen, cell):
    runtime = deepcopy(frozen['config'])
    runtime.update(strategy=frozen['strategy'], timerange=cell['timerange'], timeframe=cell['timeframe'],
                   dry_run=True, user_data_dir=str(path / 'inputs'), datadir=str(path / 'inputs/data'),
                   strategy_path=str(path / 'inputs/strategies'), recursive_strategy_search=False,
                   backtest_cache='none')
    runtime['exchange']['pair_whitelist'] = [cell['pair']]
    normalize_cli_numbers(runtime)
    (path / 'runtime.json').write_text(json.dumps(runtime, ensure_ascii=False), encoding='utf-8')
    return runtime


def _run(path):
    uid = path.name
    record = json.loads((path / 'record.json').read_text())
    try:
        record['status'] = 'running'
        _persist(path, record)
        for cell in record['cells']:
            cell_path = path / 'cells' / str(cell['index'])
            with optimization_lock, _lock:
                _sync_cancel(path, record)
                if record.get('cancel_requested_at'):
                    break
                record['current_cell'] = cell['index']
                cell['status'] = 'running'
                _persist(path, record)
            try:
                frozen_record = {'input_manifest_sha256': cell['input_manifest_sha256']}
                frozen = opt.verified_inputs(cell_path, frozen_record)
                if frozen['revision'] != record['revision'] or frozen['config']['exchange']['pair_whitelist'] != [cell['pair']]:
                    raise ValueError('Bản sao không khớp cặp hoặc mã chiến lược.')
                _runtime(cell_path, frozen, cell)
                cell['runtime_sha256'] = digest(cell_path / 'runtime.json')
                output = cell_path / 'output'
                command = [sys.executable, '-m', 'freqtrade', 'backtesting',
                           '--config', str(cell_path / 'runtime.json'), '--userdir', str(cell_path / 'inputs'),
                           '--strategy-path', str(cell_path / 'inputs/strategies'), '--datadir', str(cell_path / 'inputs/data'),
                           '--strategy', record['strategy'], '--timerange', cell['timerange'],
                           '--export', 'trades', '--backtest-directory', str(output), '--cache', 'none', '--no-color']
                with optimization_lock, _lock:
                    _sync_cancel(path, record)
                    if record.get('cancel_requested_at'):
                        cell['status'] = 'cancelled'
                        break
                    record['active_command'] = command
                    _persist(path, record)
                    with (cell_path / 'native.log').open('ab') as log:
                        process = subprocess.Popen(command, cwd=cell_path, env=opt.child_environment(),
                                                   stdin=subprocess.DEVNULL, stdout=log,
                                                   stderr=subprocess.STDOUT, start_new_session=True)
                    _owned[uid] = process
                    record['active_process_identity'] = _identity(process.pid)
                    _persist(path, record)
                process.wait()
                with optimization_lock, _lock:
                    _sync_cancel(path, record)
                    _owned.pop(uid, None)
                    record['active_process_identity'] = None
                    record['active_command'] = None
                    _persist(path, record)
                if record.get('cancel_requested_at'):
                    cell['status'] = 'cancelled'
                elif process.returncode != 0:
                    cell.update(status='failed', error=f'Engine native kết thúc mã {process.returncode}.')
                else:
                    opt.verified_inputs(cell_path, {'input_manifest_sha256': cell['input_manifest_sha256'],
                                                    'runtime_sha256': cell['runtime_sha256']})
                    result = _native_summary(cell_path, record, output)
                    cell.update(result, status='success', parameter_sha256=(frozen['files'].get(
                        'inputs/strategies/' + record['strategy'] + '.json')),
                        note='Backtest một cặp và một khung, vốn/vị thế đặt lại riêng; native có thể force-exit ở cuối khoảng.')
            except Exception as error:
                cell.update(status='failed', error=str(error))
            record['completed_cells'] += 1
            record['current_cell'] = None
            _persist(path, record)
        _sync_cancel(path, record)
        if record.get('cancel_requested_at'):
            for cell in record['cells']:
                if cell['status'] == 'pending':
                    cell['status'] = 'cancelled'
            record['status'] = 'cancelled'
        else:
            record['status'] = 'success' if all(c['status'] == 'success' for c in record['cells']) else 'incomplete'
        record['incomplete_cells'] = sum(c['status'] != 'success' for c in record['cells'])
        record['research_status'] = 'review' if record['status'] == 'success' else 'incomplete'
        record['current_cell'] = None
        record['finished_at'] = now()
        _persist(path, record)
    except Exception as error:
        record.update(status='failed', error=str(error), current_cell=None, finished_at=now(),
                      research_status='incomplete')
        _persist(path, record)
    finally:
        with optimization_lock, _lock:
            _release(uid)


@router.get('/matrix')
def list_matrix(strategy: str | None = None, config=Depends(get_config)):
    with _lock:
        if strategy:
            target(strategy, config)
        jobs = []
        for file in sorted(root(config).glob('*/record.json'), key=lambda item: item.stat().st_mtime, reverse=True):
            if file.is_symlink() or file.parent.is_symlink():
                continue
            record = _refreshed(file.parent)
            if strategy is None or strategy == record.get('strategy'):
                jobs.append(record)
            if len(jobs) >= 100:
                break
        return {'jobs': jobs}


@router.get('/matrix/{uid}')
def get_matrix(uid: str, config=Depends(get_config)):
    with _lock:
        return _refreshed(path_for(uid, config))


@router.post('/matrix/{uid}/cancel')
def cancel(uid: str, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock, _lock:
        path = path_for(uid, config)
        record = _refreshed(path)
        if record['status'] not in ACTIVE:
            return record
        if uid != _active_id:
            raise HTTPException(409, 'Không còn quyền sở hữu tiến trình ma trận; chưa gửi tín hiệu dừng.')
        record.update(status='cancelling', cancel_requested_at=record.get('cancel_requested_at') or now())
        _persist(path, record)
        process = _owned.get(uid)
        if process is not None:
            opt.stop_owned_group(process, signal.SIGINT)
            background_tasks.add_task(opt.complete_cancel, process)
        return json_safe(record)
