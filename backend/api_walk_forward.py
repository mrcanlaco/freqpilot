"""Rolling walk-forward research using only the pinned Freqtrade CLI.

Each train window owns a native Hyperopt child. Its train-selected epoch and the
untuned baseline are then backtested on the following, disjoint OOS interval.
The final holdout requires a second, explicit request. Nothing here controls a bot.
"""
import json
import re
import shutil
import signal
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zipfile import ZipFile
import math

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_optimization import (
    optimization_lock, capabilities, normalize_cli_numbers, native_command,
    child_environment, epoch_rows, epoch_public, verified_inputs, stop_owned_group,
)
from freqtrade.rpc.api_server import api_optimization as opt
from freqtrade.rpc.api_server.api_runs import digest, freeze
from freqtrade.rpc.api_server.api_studio import Manifest, json_safe, storage, write_check
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG

router = APIRouter()
ACTIVE = {'prepared', 'running', 'cancelling', 'holdout_running'}
_owned: dict[str, subprocess.Popen] = {}
_active_id: str | None = None
_lock = threading.RLock()
MAX_WINDOWS = 6
MAX_INPUT_BYTES = 6 * 1024 ** 3


def now():
    return datetime.now(timezone.utc).isoformat()


def root(config):
    directory = storage(config) / 'walk_forward'
    directory.mkdir(exist_ok=True)
    return directory


def path_for(uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(422, 'Mã thí nghiệm không hợp lệ.')
    path = root(config) / uid
    if path.is_symlink() or (path / 'record.json').is_symlink() or not (path / 'record.json').is_file():
        raise HTTPException(404, 'Không có thí nghiệm này.')
    return path


class WalkForwardRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: str
    revision: str
    preset_id: str | None = None
    settings: dict
    epochs: int = Field(ge=1, le=500)
    spaces: list[str] = Field(min_length=1, max_length=20)
    loss: str = 'SharpeHyperOptLossDaily'
    random_state: int = Field(default=42, ge=1, le=2147483647)
    min_trades: int = Field(default=10, ge=1, le=10000)
    workers: int = Field(default=1, ge=1, le=2)
    train_days: int = Field(ge=1, le=730)
    oos_days: int = Field(ge=1, le=180)
    gap_days: int = Field(default=0, ge=0, le=90)
    holdout_days: int = Field(ge=1, le=180)
    max_windows: int = Field(default=MAX_WINDOWS, ge=2, le=MAX_WINDOWS)


def _date(value):
    return value.strftime('%Y%m%d')


def _timerange(start, end):
    return _date(start) + '-' + _date(end)


def timeline(req):
    """Closed UTC dates; OOS intervals advance by their whole length."""
    raw = req.settings.get('timerange', '')
    if not isinstance(raw, str) or not re.fullmatch(r'\d{8}-\d{8}', raw):
        raise HTTPException(422, 'Chọn ngày bắt đầu và kết thúc đóng, theo UTC.')
    try:
        first = datetime.strptime(raw[:8], '%Y%m%d').replace(tzinfo=timezone.utc)
        last = datetime.strptime(raw[9:], '%Y%m%d').replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise HTTPException(422, 'Ngày UTC không hợp lệ.') from error
    holdout_start = last - timedelta(days=req.holdout_days)
    if first >= holdout_start:
        raise HTTPException(422, 'Không còn dữ liệu học và kiểm định trước holdout.')
    windows = []
    cursor = first
    while True:
        train_end = cursor + timedelta(days=req.train_days)
        oos_start = train_end + timedelta(days=req.gap_days)
        oos_end = oos_start + timedelta(days=req.oos_days)
        if oos_end > holdout_start:
            break
        if len(windows) >= req.max_windows:
            raise HTTPException(422, 'Số cửa sổ vượt giới hạn đã chọn; hãy tăng ngày OOS hoặc thu hẹp phạm vi. Không bỏ qua cửa sổ nào.')
        windows.append({'index': len(windows), 'train_timerange': _timerange(cursor, train_end),
                        'oos_timerange': _timerange(oos_start, oos_end),
                        'gap_days': req.gap_days, 'status': 'pending',
                        'baseline': None, 'candidate': None, 'hyperopt': None})
        cursor += timedelta(days=req.oos_days)
    if len(windows) < 2:
        raise HTTPException(422, 'Cần ít nhất hai cửa sổ train/OOS hoàn chỉnh trước holdout.')
    return windows, _timerange(holdout_start, last)


def validate_request(req, config):
    if req.settings.get('enable_protections'):
        raise HTTPException(422, 'Walk-forward chưa hỗ trợ bật protection vì Hyperopt native sẽ đổi giao thức.')
    caps = capabilities(req.strategy, config)
    if not caps['available']:
        raise HTTPException(422, caps['unavailable_reason'])
    schema = caps['schema']
    if schema['revision'] != req.revision:
        raise HTTPException(409, 'Mã đã đổi. Tải lại trước khi tạo thí nghiệm.')
    if len(req.spaces) != len(set(req.spaces)) or not set(req.spaces) <= {
            item['id'] for item in caps['spaces'] if item['enabled']}:
        raise HTTPException(422, 'Nhóm tham số không khả dụng cho chiến lược này.')
    if req.loss not in {item['id'] for item in caps['losses']}:
        raise HTTPException(422, 'Chỉ dùng mục tiêu chính thức của engine 2026.9.')
    # Native REST's accepted controls and numeric coercion are checked before
    # reserving a child. The frozen CLI recipe undergoes this same check again.
    from freqtrade.rpc.api_server.api_runs import reproducible_config
    normalize_cli_numbers(reproducible_config(config, req.settings, req.strategy))
    windows, holdout = timeline(req)
    return schema, windows, holdout


@router.post('/walk-forward/preview')
def preview(req: WalkForwardRequest, config=Depends(get_config)):
    schema, windows, holdout = validate_request(req, config)
    unused = _unused_tail(windows, holdout)
    bytes_estimate = _source_bytes(config)
    return {'windows': windows, 'holdout_timerange': holdout, 'unused_timerange': unused,
            'estimated_hyperopt_epochs': req.epochs * len(windows),
            'estimated_backtests': len(windows) * 2 + 2,
            'estimated_input_bytes': bytes_estimate * (len(windows) + 1),
            'max_windows': MAX_WINDOWS, 'schema_revision': schema['schema_revision'],
            'note': 'Ước lượng gồm baseline và ứng viên ở mỗi OOS, cộng hai bài thử holdout chủ động. Mỗi OOS khởi đầu không vị thế; native có thể force-exit ở cuối. Khoảng dư trước holdout được hiển thị riêng.'}


def _unused_tail(windows, holdout):
    oos_end = windows[-1]['oos_timerange'].split('-')[1]
    holdout_start = holdout.split('-')[0]
    return oos_end + '-' + holdout_start if oos_end < holdout_start else None


def _source_bytes(config):
    source = Path(config['datadir']).resolve()
    return sum(f.stat().st_size for f in source.rglob('*.feather')
               if f.is_file() and not f.is_symlink())


def _identity(pid):
    return opt.process_identity(pid)


def _orphan_alive(record):
    identity = record.get('active_process_identity')
    command = record.get('active_command')
    if not identity or not command or identity != _identity(identity['pid']):
        return False
    try:
        actual = (Path('/proc') / str(identity['pid']) / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        return actual == command
    except (OSError, UnicodeError):
        return True


def guard_wfa_orphans(config):
    """Called by the root router's native guard after a webserver restart."""
    for file in root(config).glob('*/record.json'):
        if file.is_symlink() or file.parent.is_symlink():
            continue
        record = json.loads(file.read_text())
        if record['status'] in ACTIVE or record.get('orphan_process_alive'):
            if _orphan_alive(record):
                raise HTTPException(409, 'Tiến trình walk-forward cũ vẫn còn. Chờ nó kết thúc trước khi dùng engine.')


def _ensure_idle(config):
    if _active_id is not None:
        raise HTTPException(409, 'Một thí nghiệm walk-forward đang chạy.')
    opt.ensure_idle(config)
    guard_wfa_orphans(config)


def _persist(p, record):
    write_check(p / 'record.json', record)


def _refreshed(p):
    record = json.loads((p / 'record.json').read_text())
    if record['status'] in ACTIVE and record['id'] != _active_id:
        record.update(status='interrupted', finished_at=now(),
                      orphan_process_alive=_orphan_alive(record),
                      error='Dịch vụ khởi động lại; thí nghiệm không được tự chạy tiếp.')
        _persist(p, record)
    elif record['status'] == 'interrupted' and record.get('orphan_process_alive') and not _orphan_alive(record):
        record['orphan_process_alive'] = False
        _persist(p, record)
    return json_safe(record)


def _reserve(uid):
    global _active_id
    _active_id = uid
    opt._active_id = 'wfa:' + uid  # legacy backtest/download/analysis guards
    ApiBG.analysis_running = True


def _release(uid):
    global _active_id
    _owned.pop(uid, None)
    if _active_id == uid:
        _active_id = None
        if opt._active_id == 'wfa:' + uid:
            opt._active_id = None
        ApiBG.analysis_running = False


@router.post('/walk-forward')
def start(req: WalkForwardRequest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock, _lock:
        _ensure_idle(config)
        schema, windows, holdout = validate_request(req, config)
        if _source_bytes(config) * (len(windows) + 1) > MAX_INPUT_BYTES:
            raise HTTPException(422, 'Dự kiến bản sao dữ liệu vượt ngân sách 6 GiB; hãy thu hẹp phạm vi hoặc số cửa sổ.')
        p, frozen_record = freeze(Manifest(strategy=req.strategy, revision=req.revision,
                                            settings=req.settings, preset_id=req.preset_id), config)
        destination = root(config) / frozen_record['id']
        p.rename(destination)
        p = destination
        frozen = json.loads((p / 'inputs.json').read_text())
        input_bytes = frozen_record['input_bytes']
        if input_bytes * (len(windows) + 1) > MAX_INPUT_BYTES:
            record = {'id': p.name, 'strategy': req.strategy, 'status': 'failed',
                      'error': 'Bản sao dữ liệu cho các cửa sổ vượt ngân sách 6 GiB.',
                      'created_at': now(), 'finished_at': now()}
            _persist(p, record)
            raise HTTPException(422, record['error'])
        record = {k: frozen_record[k] for k in ('id', 'strategy', 'revision', 'engine', 'created_at',
                                                'settings', 'input_manifest_sha256', 'input_files', 'input_bytes')}
        record.update(status='prepared', windows=windows, holdout_timerange=holdout,
                      unused_timerange=_unused_tail(windows, holdout),
                      holdout_status='sealed', holdout=None, schema=schema,
                      epochs=req.epochs, spaces=req.spaces, loss=req.loss,
                      random_state=req.random_state, min_trades=req.min_trades,
                      workers=req.workers, train_days=req.train_days, oos_days=req.oos_days,
                      gap_days=req.gap_days, preset=frozen.get('preset'),
                      selection_rule='lowest eligible native train loss; latest window for holdout',
                      current_stage=None, completed_windows=0, cancel_requested_at=None,
                      active_process_identity=None, active_command=None, error=None,
                      estimated_hyperopt_epochs=req.epochs * len(windows),
                      estimated_backtests=len(windows) * 2 + 2,
                      estimated_input_bytes=input_bytes * (len(windows) + 1),
                      note='OOS độc lập, không carry vị thế; holdout chỉ chạy sau thao tác riêng.')
        _persist(p, record)
        _reserve(p.name)
        background_tasks.add_task(_run_windows, p, config)
        return json_safe(record)


def _copy_inputs(source, destination, frozen):
    (destination / 'inputs').mkdir(parents=True)
    for name, expected in frozen['files'].items():
        if not name.startswith('inputs/') or '..' in Path(name).parts:
            raise ValueError('Đường dẫn bản lưu không hợp lệ.')
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
        if digest(target) != expected:
            raise ValueError('Đầu vào thay đổi khi tạo cửa sổ: ' + name)
    (destination / 'inputs/hyperopt_results').mkdir()


def _runtime(p, original, timerange, strategy):
    runtime = deepcopy(original)
    runtime.update(strategy=strategy, timerange=timerange, dry_run=True,
                   user_data_dir=str(p / 'inputs'), datadir=str(p / 'inputs/data'),
                   strategy_path=str(p / 'inputs/strategies'), recursive_strategy_search=False,
                   backtest_cache='none')
    normalize_cli_numbers(runtime)
    (p / 'runtime.json').write_text(json.dumps(runtime, ensure_ascii=False), encoding='utf-8')
    return runtime


def _command_backtest(p, record, timerange, output):
    return [sys.executable, '-m', 'freqtrade', 'backtesting', '--config', str(p / 'runtime.json'),
            '--userdir', str(p / 'inputs'), '--strategy-path', str(p / 'inputs/strategies'),
            '--datadir', str(p / 'inputs/data'), '--strategy', record['strategy'],
            '--timerange', timerange, '--export', 'trades', '--backtest-directory', str(output),
            '--cache', 'none', '--no-color']


def _child(p, record, command, stage):
    uid = record['id']
    with optimization_lock, _lock:
        _sync_cancel(p, record)
        if record.get('cancel_requested_at'):
            return False
        record.update(current_stage=stage, active_command=command)
        _persist(p, record)
        with (p / 'native.log').open('ab') as log:
            process = subprocess.Popen(command, cwd=p, env=child_environment(),
                                       stdin=subprocess.DEVNULL, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        _owned[uid] = process
        record['active_process_identity'] = _identity(process.pid)
        _persist(p, record)
    process.wait()
    with optimization_lock, _lock:
        _sync_cancel(p, record)
        _owned.pop(uid, None)
        record['active_process_identity'] = None
        record['active_command'] = None
        _persist(p, record)
    return process.returncode == 0 and not record.get('cancel_requested_at')


def _sync_cancel(p, record):
    persisted = json.loads((p / 'record.json').read_text())
    if persisted.get('cancel_requested_at'):
        record['cancel_requested_at'] = persisted['cancel_requested_at']
        record['status'] = 'cancelling'


def _native_summary(p, record, output):
    archives = list(output.glob('*.zip'))
    if len(archives) != 1 or archives[0].is_symlink():
        raise ValueError('Backtest native chưa xuất đúng một ZIP.')
    archive = archives[0]
    with ZipFile(archive) as bundle:
        source = bundle.read(archive.stem + '_' + record['strategy'] + '.py')
        import hashlib
        if hashlib.sha256(source).hexdigest() != record['revision']:
            raise ValueError('Mã trong ZIP native khác bản nguồn.')
        parameters = p / 'inputs/strategies' / (record['strategy'] + '.json')
        if parameters.is_file():
            embedded = bundle.read(archive.stem + '_' + record['strategy'] + '.json')
            if hashlib.sha256(embedded).hexdigest() != digest(parameters):
                raise ValueError('Tham số trong ZIP native khác bản dùng khi chạy.')
        stats = json.loads(bundle.read(archive.stem + '.json'))['strategy'][record['strategy']]
    fields = ('total_trades', 'profit_total_abs', 'profit_total', 'max_drawdown_account',
              'profit_factor', 'wins', 'losses', 'backtest_start', 'backtest_end',
              'timeframe', 'total_volume', 'fee_total')
    reasons = stats.get('exit_reason_summary') or []
    forced = sum(int(item.get('trades', 0)) for item in reasons if item.get('key') == 'force_exit')
    summary = {key: stats.get(key) for key in fields}
    if summary['total_trades'] == 0:
        summary['profit_factor'] = None  # native 0/0 is not a measured ratio
    return json_safe({'artifact': archive.relative_to(p.parent.parent).as_posix(),
                      'artifact_sha256': digest(archive),
                      'summary': summary, 'force_exit_trades': forced,
                      'native_backtest_start': stats.get('backtest_start'),
                      'native_backtest_end': stats.get('backtest_end'),
                      'note': 'OOS là backtest độc lập; native có thể force-exit ở ranh giới.'})


def _comparison(window):
    baseline, candidate, hyperopt = window['baseline'], window['candidate'], window['hyperopt']
    if not baseline or not candidate or not hyperopt or baseline['status'] != 'success' or candidate['status'] != 'success':
        return None
    train = (hyperopt.get('best_epoch') or {}).get('metrics') or {}
    oos = candidate['summary']
    base = baseline['summary']
    train_pnl, oos_pnl, baseline_pnl = (train.get('profit_total_abs'),
                                       oos.get('profit_total_abs'), base.get('profit_total_abs'))
    if not all(type(v) in (int, float) and math.isfinite(v) for v in (train_pnl, oos_pnl, baseline_pnl)):
        return None
    train_start, train_end = window['train_timerange'].split('-')
    oos_start, oos_end = window['oos_timerange'].split('-')
    train_days = (datetime.strptime(train_end, '%Y%m%d') - datetime.strptime(train_start, '%Y%m%d')).days
    oos_days = (datetime.strptime(oos_end, '%Y%m%d') - datetime.strptime(oos_start, '%Y%m%d')).days
    return {'train_profit_abs_usdt': train_pnl, 'oos_profit_abs_usdt': oos_pnl,
            'baseline_oos_profit_abs_usdt': baseline_pnl,
            'candidate_minus_baseline_oos_usdt': oos_pnl - baseline_pnl,
            'train_daily_usdt': train_pnl / train_days,
            'oos_daily_usdt': oos_pnl / oos_days,
            'oos_minus_train_daily_usdt': oos_pnl / oos_days - train_pnl / train_days,
            'method': 'Mỗi cửa sổ khởi động vốn và vị thế độc lập; USDT/ngày chỉ là chuẩn hóa mô tả, không phải đường vốn liên tục.'}


def _backtest(p, record, base, timerange, variant, row=None):
    from freqtrade.optimize.hyperopt_tools import HyperoptTools
    output = p / ('backtest_' + variant)
    output.mkdir()
    parameter = p / 'inputs/strategies' / (record['strategy'] + '.json')
    if row is not None:
        HyperoptTools.export_params(row, record['strategy'], parameter)
        parameter_sha = digest(parameter)
    else:
        original = base / 'inputs/strategies' / (record['strategy'] + '.json')
        if original.is_file():
            shutil.copyfile(original, parameter)
            parameter_sha = digest(parameter)
        else:
            parameter.unlink(missing_ok=True)
            parameter_sha = None
    _runtime(p, json.loads((base / 'inputs.json').read_text())['config'], timerange, record['strategy'])
    shutil.copyfile(p / 'runtime.json', output / 'runtime.json')
    runtime_sha = digest(output / 'runtime.json')
    command = _command_backtest(p, record, timerange, output)
    if not _child(base, record, command, f'{p.name}:{variant}:{timerange}'):
        return {'status': 'cancelled' if record.get('cancel_requested_at') else 'failed',
                'error': 'Backtest native chưa hoàn tất.', 'timerange': timerange,
                'parameter_sha256': parameter_sha, 'runtime_sha256': runtime_sha}
    result = _native_summary(p, record, output)
    result.update(status='success', timerange=timerange, parameter_sha256=parameter_sha,
                  runtime_sha256=runtime_sha)
    return result


def _run_windows(p, config):
    uid = p.name
    record = json.loads((p / 'record.json').read_text())
    try:
        verified_inputs(p, record)
        frozen = json.loads((p / 'inputs.json').read_text())
        _sync_cancel(p, record)
        if record.get('cancel_requested_at'):
            record.update(status='cancelled', finished_at=now())
            _persist(p, record)
            return
        record['status'] = 'running'
        _persist(p, record)
        for window in record['windows']:
            _sync_cancel(p, record)
            if record.get('cancel_requested_at'):
                break
            window['status'] = 'running'
            _persist(p, record)
            target = p / 'windows' / str(window['index'])
            target.mkdir(parents=True)
            _copy_inputs(p, target, frozen)
            train = window['train_timerange']
            oos = window['oos_timerange']
            baseline = _backtest(target, record, p, oos, 'baseline')
            window['baseline'] = baseline
            _persist(p, record)
            _sync_cancel(p, record)
            if record.get('cancel_requested_at'):
                window['status'] = 'cancelled'
                record['completed_windows'] += 1
                _persist(p, record)
                break
            _runtime(target, frozen['config'], train, record['strategy'])
            shutil.copyfile(target / 'runtime.json', target / 'hyperopt_runtime.json')
            hyperopt_runtime_sha = digest(target / 'hyperopt_runtime.json')
            hyper = {key: record[key] for key in ('strategy', 'epochs', 'spaces', 'loss',
                                                  'random_state', 'min_trades', 'workers')}
            command = native_command(target, hyper)
            succeeded = _child(p, record, command, f'window:{window["index"]}:hyperopt')
            try:
                rows = epoch_rows(target, hyper, terminal=succeeded)
                public = [epoch_public(row, hyper) for row in rows]
                eligible = [row for row in public if row['eligible']]
                best = min(eligible, key=lambda row: (row['loss'], row['epoch'])) if eligible else None
                result = next(iter((target / 'inputs/hyperopt_results').glob('*.fthypt')), None)
                window['hyperopt'] = {'status': 'success' if succeeded else ('cancelled' if record.get('cancel_requested_at') else 'failed'),
                                      'completed_epochs': len(rows), 'best_epoch': best,
                                      'result_sha256': digest(result) if result else None,
                                      'result_file': result.relative_to(p).as_posix() if result else None,
                                      'runtime_sha256': hyperopt_runtime_sha,
                                      'eligible_epochs': len(eligible), 'seed': record['random_state']}
                _sync_cancel(p, record)
                if best and succeeded and not record.get('cancel_requested_at'):
                    chosen = next(row for row in rows if row['current_epoch'] == best['epoch'])
                    try:
                        opt.epoch_values(chosen, record['schema'])
                        window['candidate'] = _backtest(target, record, p, oos, 'candidate', chosen)
                        window['candidate']['epoch'] = best['epoch']
                    except Exception as error:
                        window['candidate'] = {'status': 'failed', 'epoch': best['epoch'],
                                               'error': str(error)}
                elif succeeded:
                    window['candidate'] = {'status': 'ineligible', 'error': 'Không có epoch train hợp lệ.'}
            except Exception as error:
                window['hyperopt'] = {'status': 'failed', 'error': str(error)}
                window['candidate'] = {'status': 'unavailable', 'error': 'Không xác minh được kết quả Hyperopt.'}
            window['comparison'] = _comparison(window)
            window['status'] = ('cancelled' if record.get('cancel_requested_at') else
                                'success' if window['baseline']['status'] == 'success' and
                                window['candidate'] and window['candidate']['status'] == 'success' else 'incomplete')
            record['completed_windows'] += 1
            _persist(p, record)
        _sync_cancel(p, record)
        record['status'] = 'cancelled' if record.get('cancel_requested_at') else 'success'
        record['incomplete_windows'] = sum(w['status'] != 'success' for w in record['windows'])
        record['research_status'] = 'incomplete' if record['incomplete_windows'] else 'review'
        record['summary'] = {'evaluated_windows': record['completed_windows'],
                             'complete_windows': len(record['windows']) - record['incomplete_windows'],
                             'eligible_candidates': sum((w.get('candidate') or {}).get('status') == 'success'
                                                        for w in record['windows']),
                             'note': 'Không cộng % lợi nhuận, Sharpe hoặc drawdown của các OOS độc lập thành hiệu suất danh mục.'}
        record['current_stage'] = None
        record['finished_at'] = now()
        _persist(p, record)
    except Exception as error:
        record.update(status='failed', error=str(error), finished_at=now(), current_stage=None)
        _persist(p, record)
    finally:
        with optimization_lock, _lock:
            _release(uid)


@router.get('/walk-forward')
def list_walk_forward(strategy: str | None = None, config=Depends(get_config)):
    with _lock:
        records = []
        for file in sorted(root(config).glob('*/record.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            if file.is_symlink() or file.parent.is_symlink():
                continue
            record = _refreshed(file.parent)
            if strategy is None or strategy == record.get('strategy'):
                records.append(record)
            if len(records) >= 100:
                break
        return {'jobs': records, 'experiments': records}


@router.get('/walk-forward/{uid}')
def get_walk_forward(uid: str, config=Depends(get_config)):
    with _lock:
        return _refreshed(path_for(uid, config))


@router.post('/walk-forward/{uid}/cancel')
def cancel(uid: str, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock, _lock:
        p = path_for(uid, config)
        record = _refreshed(p)
        if record['status'] not in ACTIVE:
            return record
        if uid != _active_id:
            raise HTTPException(409, 'Không còn quyền sở hữu tiến trình; chưa gửi tín hiệu dừng.')
        record.update(status='cancelling', cancel_requested_at=record.get('cancel_requested_at') or now())
        _persist(p, record)
        process = _owned.get(uid)
        if process is not None:
            stop_owned_group(process, signal.SIGINT)
            background_tasks.add_task(opt.complete_cancel, process)
        return json_safe(record)


@router.post('/walk-forward/{uid}/holdout')
def evaluate_holdout(uid: str, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock, _lock:
        _ensure_idle(config)
        p = path_for(uid, config)
        record = _refreshed(p)
        if record['status'] != 'success' or record['holdout_status'] not in {'sealed', 'success', 'incomplete', 'cancelled'}:
            raise HTTPException(409, 'Chuỗi cửa sổ chưa hoàn tất để mở holdout.')
        # This rule reads only train Hyperopt validity/order. OOS P&L and even
        # an OOS infrastructure failure cannot promote a different parameter.
        winners = [w for w in record['windows'] if (w.get('hyperopt') or {}).get('status') == 'success'
                   and (w['hyperopt'].get('best_epoch') or {}).get('eligible')]
        if not winners:
            raise HTTPException(422, 'Không có ứng viên train hợp lệ cho holdout.')
        if record.get('holdout'):
            record.setdefault('holdout_history', []).append(record['holdout'])
        record['holdout_attempts'] = record.get('holdout_attempts', 0) + 1
        record['holdout_status'] = 'running'
        record['status'] = 'holdout_running'
        record['cancel_requested_at'] = None
        record['holdout_selection'] = {'window': winners[-1]['index'],
                                       'epoch': winners[-1]['hyperopt']['best_epoch']['epoch'],
                                       'rule': 'latest successful train winner; no OOS reranking'}
        _persist(p, record)
        _reserve(uid)
        background_tasks.add_task(_run_holdout, p)
        return json_safe(record)


def _run_holdout(p):
    uid = p.name
    record = json.loads((p / 'record.json').read_text())
    try:
        verified_inputs(p, record)
        frozen = json.loads((p / 'inputs.json').read_text())
        selected = record['holdout_selection']
        train_target = p / 'windows' / str(selected['window'])
        expected_result = record['windows'][selected['window']]['hyperopt']['result_sha256']
        result_file = next(iter((train_target / 'inputs/hyperopt_results').glob('*.fthypt')), None)
        if result_file is None or digest(result_file) != expected_result:
            raise ValueError('Kết quả train dùng để chọn ứng viên đã thay đổi.')
        hyper = {key: record[key] for key in ('epochs', 'min_trades')}
        rows = epoch_rows(train_target, hyper, terminal=True)
        chosen = next(row for row in rows if row['current_epoch'] == selected['epoch'])
        if not epoch_public(chosen, hyper)['eligible']:
            raise ValueError('Ứng viên train đã lưu không còn hợp lệ.')
        opt.epoch_values(chosen, record['schema'])
        target = p / 'holdout' / str(record['holdout_attempts'])
        target.mkdir(parents=True)
        _copy_inputs(p, target, frozen)
        timerange = record['holdout_timerange']
        baseline = _backtest(target, record, p, timerange, 'baseline')
        record['holdout'] = {'baseline': baseline, 'candidate': None,
                             'timerange': timerange, 'selection': selected,
                             'attempt': record['holdout_attempts']}
        _persist(p, record)
        _sync_cancel(p, record)
        if not record.get('cancel_requested_at'):
            record['holdout']['candidate'] = _backtest(target, record, p, timerange, 'candidate', chosen)
        record['holdout_status'] = ('cancelled' if record.get('cancel_requested_at') else
                                    'success' if baseline['status'] == 'success' and
                                    record['holdout']['candidate']['status'] == 'success' else 'incomplete')
        record['status'] = 'success'
        record['finished_at'] = now()
        record['current_stage'] = None
        _persist(p, record)
    except Exception as error:
        record.update(status='success', holdout_status='incomplete', holdout_error=str(error),
                      finished_at=now(), current_stage=None)
        _persist(p, record)
    finally:
        with optimization_lock, _lock:
            _release(uid)
