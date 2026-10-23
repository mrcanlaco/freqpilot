"""Explicit native Hyperopt jobs over private, frozen research inputs.

The engine and its fill/loss/optimizer implementations are unmodified. A native CLI
child owns its process group; cancellation can never target a paper worker.
"""
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ConfigDict

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import read, target
from freqtrade.rpc.api_server.api_studio import Manifest, storage, write_check, json_safe
from freqtrade.rpc.api_server.api_runs import digest, freeze, run_root, launch_snapshot
from freqtrade.rpc.api_server.api_presets import (
    inspect_parameters, validate_values, preset_root, preset_lock, sha,
)
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG

router = APIRouter()
optimization_lock = threading.RLock()
_processes: dict[str, subprocess.Popen] = {}
_active_id: str | None = None
ACTIVE = {'prepared', 'running', 'cancelling'}
TERMINAL = {'success', 'cancelled', 'failed', 'interrupted'}
METRICS = ('total_trades', 'profit_total_abs', 'profit_total', 'max_drawdown_account', 'profit_factor')
BUILTINS = {
    'roi': ('ROI', ('minimal_roi',)),
    'stoploss': ('Cắt lỗ', ('stoploss',)),
    'trailing': ('Trailing stop', ('trailing_stop', 'trailing_stop_positive',
                 'trailing_stop_positive_offset', 'trailing_only_offset_is_reached')),
}
LOSS_LABELS = {'SharpeHyperOptLossDaily': 'Sharpe theo ngày',
               'SortinoHyperOptLossDaily': 'Sortino theo ngày',
               'OnlyProfitHyperOptLoss': 'Lợi nhuận ròng', 'CalmarHyperOptLoss': 'Calmar',
               'ProfitDrawDownHyperOptLoss': 'Lợi nhuận và drawdown'}


def now():
    return datetime.now(timezone.utc).isoformat()


def optimization_root(config):
    p = storage(config) / 'optimizations'
    p.mkdir(exist_ok=True)
    return p


def optimization_path(uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(422, 'Mã phiên tối ưu không hợp lệ.')
    p = optimization_root(config) / uid
    if p.is_symlink() or (p / 'record.json').is_symlink() or not (p / 'record.json').is_file():
        raise HTTPException(404, 'Không có phiên tối ưu này.')
    return p


def process_identity(pid):
    try:
        stat = Path('/proc') / str(pid) / 'stat'
        # comm may contain spaces or parentheses; fields following its last ')' start at field 3.
        fields = stat.read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'start_ticks': fields[19]}
    except (OSError, IndexError):
        return None


def orphan_alive(p, record):
    identity = record.get('process_identity')
    if not identity or identity != process_identity(identity['pid']):
        return False
    try:
        command = (Path('/proc') / str(identity['pid']) / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        return command == native_command(p, record)
    except (OSError, UnicodeError):
        return True  # uncertain ownership must never allow a competing job


def ensure_idle(config=None):
    if _active_id is not None or ApiBG.analysis_running or ApiBG.download_data_running:
        raise HTTPException(409, 'Chờ tác vụ nghiên cứu hoặc tải dữ liệu hiện tại hoàn tất.')
    if config is not None:
        for file in optimization_root(config).glob('*/record.json'):
            if file.is_symlink() or file.parent.is_symlink():
                continue
            record = json.loads(file.read_text())
            if record['status'] in ACTIVE or record.get('orphan_process_alive'):
                if orphan_alive(file.parent, record):
                    raise HTTPException(409, 'Còn tiến trình tối ưu của phiên trước. Khởi động lại riêng dịch vụ nghiên cứu để thu hồi nó trước khi chạy tiếp.')
        # Other native child coordinators share this engine. A webserver
        # restart can clear in-memory flags while their owned subprocess lives.
        from freqtrade.rpc.api_server.api_walk_forward import guard_wfa_orphans
        from freqtrade.rpc.api_server.api_sensitivity import guard_sensitivity_orphans
        from freqtrade.rpc.api_server.api_parameter_scope import guard_seed_orphans
        from freqtrade.rpc.api_server.api_matrix import guard_matrix_orphans
        guard_wfa_orphans(config)
        guard_sensitivity_orphans(config)
        guard_seed_orphans(config)
        guard_matrix_orphans(config)


def guard_native_research(request: Request, config=Depends(get_config)):
    """Adapter-only guard for legacy controls while the native flag is reserved.

Native backtest abort assumes a Backtesting object, and data download uses a
different flag. Neither control may act on an optimization's ownership.
"""
    guarded = ((request.method == 'POST' and request.url.path.rstrip('/').rsplit('/', 1)[-1]
                in {'backtest', 'lookahead_analysis', 'recursive_analysis', 'download_data'})
               or (request.method in {'GET', 'DELETE'} and request.url.path.endswith('/backtest'))
               or request.url.path.endswith('/backtest/abort'))
    if guarded:
        with optimization_lock:
            if _active_id is not None:
                raise HTTPException(409, 'Đang tối ưu tham số. Dùng nút dừng của chính phiên tối ưu hoặc chờ hoàn tất.')
            for file in optimization_root(config).glob('*/record.json'):
                if file.is_symlink() or file.parent.is_symlink():
                    continue
                record = json.loads(file.read_text())
                if (record['status'] in ACTIVE or record.get('orphan_process_alive')) and orphan_alive(file.parent, record):
                    raise HTTPException(409, 'Còn tiến trình tối ưu của phiên trước; chưa nhận tác vụ engine mới.')


@router.get('/optimization-capabilities/{strategy}')
def capabilities(strategy: str, config=Depends(get_config)):
    with optimization_lock:
        schema = inspect_parameters(strategy, config)
        groups = sorted({p['space'] for p in schema['fields']})
        use_exit_signal = True
        if 'sell' in groups:
            from freqtrade.resolvers.strategy_resolver import StrategyResolver
            native_strategy = StrategyResolver.load_strategy({**deepcopy(config), 'strategy': strategy})
            use_exit_signal = bool(native_strategy.use_exit_signal)
        spaces = []
        for group in groups:
            fields = [p for p in schema['fields'] if p['space'] == group and p['optimize']]
            enabled = bool(fields) and all(p['load'] for p in fields)
            reason = None if enabled else ('Có tham số optimize=true nhưng load=false; không thể nạp lại chính xác.'
                                            if fields else 'Chưa có tham số optimize=true.')
            if group == 'protection':
                enabled, reason = False, 'Chưa tối ưu protection: native tự bật bảo vệ, làm thay đổi giao thức kiểm định.'
            if group == 'sell' and not use_exit_signal:
                enabled, reason = False, 'Chiến lược đang tắt use_exit_signal; native Hyperopt nhóm sell tự bật nó.'
            spaces.append({'id': group, 'label': group, 'enabled': enabled, 'reason': reason})
        for group, (label, keys) in BUILTINS.items():
            overridden = [k for k in keys if k in config and config[k] is not None]
            spaces.append({'id': group, 'label': label, 'enabled': not overridden,
                           'reason': ('Cấu hình đang cố định ' + ', '.join(overridden) + '.') if overridden else None})
        from freqtrade.constants import HYPEROPT_LOSS_BUILTIN
        missing = [n for n in ('optuna', 'joblib', 'scipy', 'filelock') if not importlib.util.find_spec(n)]
        return {'schema': schema, 'spaces': spaces,
                'losses': [{'id': n, 'label': LOSS_LABELS.get(n, n)} for n in HYPEROPT_LOSS_BUILTIN],
                'sampler': 'NSGAIIISampler (native default; strategy may customize)',
                'max_epochs': 500, 'max_workers': 2, 'available': not missing,
                'unavailable_reason': ('Thiếu thư viện native: ' + ', '.join(missing)) if missing else None,
                'note': 'Chỉ tối ưu khi bấm chạy. Kết quả trên tập học chưa phải kiểm định ngoài mẫu.'}


class OptimizationStart(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: str
    revision: str
    preset_id: str | None = None
    settings: dict
    epochs: int = Field(default=50, ge=1, le=500)
    spaces: list[str] = Field(min_length=1, max_length=20)
    loss: str = 'SharpeHyperOptLossDaily'
    random_state: int = Field(default=42, ge=1, le=2147483647)
    min_trades: int = Field(default=10, ge=1, le=10000)
    workers: int = Field(default=1, ge=1, le=2)
    validation: Literal['single', 'split'] = 'split'
    split_date: str | None = None


def ranges(req):
    from freqtrade.configuration import TimeRange
    try:
        raw = req.settings.get('timerange', '')
        if not re.fullmatch(r'\d{8}-\d{8}', raw):
            raise ValueError('Chọn ngày bắt đầu và kết thúc rõ ràng trước khi tối ưu.')
        bounds = TimeRange.parse_timerange(raw)
        if not bounds.startts or not bounds.stopts or bounds.startts >= bounds.stopts:
            raise ValueError('Khoảng dữ liệu không hợp lệ.')
        if req.validation == 'single':
            return raw, None
        if not req.split_date or not re.fullmatch(r'(\d{4}-\d{2}-\d{2}|\d{8})', req.split_date):
            raise ValueError('Chọn ngày tách tập học và kiểm định ngoài mẫu.')
        split = datetime.strptime(req.split_date.replace('-', ''), '%Y%m%d').replace(tzinfo=timezone.utc)
        if not bounds.startts < split.timestamp() < bounds.stopts:
            raise ValueError('Ngày tách phải nằm giữa ngày bắt đầu và kết thúc.')
        compact = split.strftime('%Y%m%d')
        start, end = raw.split('-')
        return start + '-' + compact, compact + '-' + end
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


def child_environment():
    # Native env configuration must not override a reviewed frozen recipe.
    return {k: v for k, v in os.environ.items() if not k.upper().startswith('FREQTRADE_')}


def native_command(p, record):
    inputs = p / 'inputs'
    return [sys.executable, '-m', 'freqtrade', 'hyperopt', '--config', str(p / 'runtime.json'),
            '--userdir', str(inputs), '--strategy-path', str(inputs / 'strategies'),
            '--datadir', str(inputs / 'data'), '--strategy', record['strategy'],
            '--epochs', str(record['epochs']), '--spaces', *record['spaces'],
            '--hyperopt-loss', record['loss'], '--random-state', str(record['random_state']),
            '--job-workers', str(record['workers']), '--min-trades', str(record['min_trades']),
            '--disable-param-export', '--analyze-per-epoch', '--no-color']


def normalize_cli_numbers(runtime):
    """Match native REST coercion before handing its recipe to the stricter CLI.

FreqUI's native request represents stake_amount as a string. The REST backtest
launcher converts it to float, whereas configuration JSON accepts a number or
the literal 'unlimited'. Keep the archived request intact and normalize only the
private CLI recipe, using the native request model for the other numeric fields.
"""
    from freqtrade.rpc.api_server.api_schemas import BacktestRequest
    parsed = BacktestRequest(strategy=runtime['strategy'],
                            enable_protections=runtime.get('enable_protections', False),
                            stake_amount=runtime.get('stake_amount'),
                            dry_run_wallet=runtime.get('dry_run_wallet'),
                            max_open_trades=runtime.get('max_open_trades'))
    if parsed.stake_amount is not None:
        runtime['stake_amount'] = (parsed.stake_amount if parsed.stake_amount == 'unlimited'
                                   else float(parsed.stake_amount))
        if runtime['stake_amount'] != 'unlimited' and (not finite(runtime['stake_amount']) or runtime['stake_amount'] <= 0):
            raise HTTPException(422, 'Số tiền mỗi lệnh phải là số hữu hạn lớn hơn 0.')
    if parsed.dry_run_wallet is not None:
        runtime['dry_run_wallet'] = parsed.dry_run_wallet
        if not finite(runtime['dry_run_wallet']) or runtime['dry_run_wallet'] <= 0:
            raise HTTPException(422, 'Vốn mô phỏng phải là số hữu hạn lớn hơn 0.')
    if parsed.max_open_trades is not None:
        if (not finite(parsed.max_open_trades) or parsed.max_open_trades != int(parsed.max_open_trades)
                or not 1 <= parsed.max_open_trades <= 10):
            raise HTTPException(422, 'Số lệnh tối đa phải là số nguyên từ 1 đến 10.')
        runtime['max_open_trades'] = int(parsed.max_open_trades)
    return runtime


def verified_inputs(p, record):
    try:
        file = p / 'inputs.json'
        if file.is_symlink() or digest(file) != record['input_manifest_sha256']:
            raise ValueError('Hồ sơ đầu vào tối ưu đã thay đổi.')
        frozen = json.loads(file.read_text())
        if record.get('runtime_sha256') and digest(p / 'runtime.json') != record['runtime_sha256']:
            raise ValueError('Cấu hình native đã thay đổi.')
        for name, expected in frozen['files'].items():
            member = Path(name)
            full = p / member
            if member.is_absolute() or '..' in member.parts or not member.parts or member.parts[0] != 'inputs':
                raise ValueError('Đường dẫn đầu vào tối ưu không hợp lệ.')
            if full.is_symlink() or not full.resolve().is_relative_to((p / 'inputs').resolve()) or digest(full) != expected:
                raise ValueError('Bản sao đầu vào tối ưu đã thay đổi: ' + name)
        return frozen
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise HTTPException(409, 'Không xác minh được đầu vào đã đóng băng của phiên tối ưu.') from e


def result_file(p, record, terminal=False):
    folder = p / 'inputs/hyperopt_results'
    files = list(folder.glob('*.fthypt'))
    if not files:
        return None
    if len(files) != 1 or files[0].is_symlink() or files[0].resolve().parent != folder.resolve():
        raise ValueError('Engine chưa xuất đúng một tệp kết quả Hyperopt.')
    result = files[0]
    if terminal and record.get('result_sha256') and digest(result) != record['result_sha256']:
        raise ValueError('Kết quả Hyperopt đã thay đổi sau khi hoàn tất.')
    return result


def epoch_rows(p, record, terminal=False):
    path = result_file(p, record, terminal)
    if path is None:
        return []
    import rapidjson
    rows, seen = [], set()
    with path.open('rb') as stream:
        for line in stream:
            if len(line) > 20_000_000:
                raise ValueError('Một epoch vượt giới hạn đọc kết quả.')
            if not line.endswith(b'\n'):
                if terminal:
                    raise ValueError('Epoch cuối chưa được ghi hoàn chỉnh.')
                break
            row = rapidjson.loads(line)
            epoch = row.get('current_epoch')
            if (row.get('fthypt_fileversion') != 2 or type(epoch) is not int or epoch < 1
                    or epoch > record['epochs'] or epoch in seen or not isinstance(row.get('results_metrics'), dict)
                    or not isinstance(row.get('params_details'), dict) or not isinstance(row.get('params_not_optimized'), dict)):
                raise ValueError('Kết quả Hyperopt không đúng định dạng native 2026.9.')
            seen.add(epoch)
            rows.append(row)
            if len(rows) > record['epochs']:
                raise ValueError('Engine xuất quá số epoch đã yêu cầu.')
    return rows


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def epoch_public(row, record):
    stats = row['results_metrics']
    count, loss = stats.get('total_trades'), row.get('loss')
    eligible = (type(count) is int and count >= record['min_trades']
                and finite(loss) and loss < 100000)
    return json_safe({'epoch': row['current_epoch'], 'loss': loss if finite(loss) else None,
                      'eligible': eligible, 'params_details': row['params_details'],
                      'metrics': {k: stats.get(k) if finite(stats.get(k)) else None for k in METRICS}})


def update_progress(p, record, terminal=False):
    rows = epoch_rows(p, record, terminal)
    public = [epoch_public(row, record) for row in rows]
    eligible = [row for row in public if row['eligible']]
    record['completed_epochs'] = len(rows)
    record['best_epoch'] = min(eligible, key=lambda row: row['loss']) if eligible else None
    return rows


def release(uid):
    global _active_id
    _processes.pop(uid, None)
    if _active_id == uid:
        _active_id = None
        ApiBG.analysis_running = False


def finish_process(p, process):
    """A BackgroundTasks thread joins exactly the child accepted by this process."""
    uid = p.name
    try:
        process.wait()
        with optimization_lock:
            record = json.loads((p / 'record.json').read_text())
            record['finished_at'] = now()
            try:
                verified_inputs(p, record)
                rows = update_progress(p, record, terminal=True)
                path = result_file(p, record)
                if path:
                    record['result_sha256'] = digest(path)
                if record.get('cancel_requested_at'):
                    record.update(status='cancelled', error=None)
                elif process.returncode != 0:
                    record.update(status='failed', error='Tiến trình Hyperopt native không hoàn tất. Xem nhật ký cục bộ của phiên.')
                elif not rows:
                    record.update(status='failed', error='Engine không xuất epoch nào; chưa có kết quả để đánh giá.')
                else:
                    record.update(status='success', error=None)
            except Exception:
                record.update(status='failed', error='Không xác minh được đầu vào hoặc kết quả native của phiên tối ưu.')
            write_check(p / 'record.json', record)
    finally:
        with optimization_lock:
            release(uid)


def refreshed(p):
    record = json.loads((p / 'record.json').read_text())
    if record['status'] == 'interrupted' and record.get('orphan_process_alive'):
        # Lost ownership remains interrupted even when the native child later
        # exits; retire only the observed resource block, never infer success.
        if not orphan_alive(p, record):
            record['orphan_process_alive'] = False
            write_check(p / 'record.json', record)
    if record['status'] in ACTIVE:
        process = _processes.get(record['id'])
        if process is None:
            # A persisted PID alone never proves ownership or authorizes a signal.
            record.update(status='interrupted', finished_at=now(),
                          orphan_process_alive=orphan_alive(p, record),
                          error='Dịch vụ đã khởi động lại; không còn handle tiến trình để xác nhận phiên này.')
            write_check(p / 'record.json', record)
        else:
            try:
                update_progress(p, record)
            except Exception:
                record['progress_unavailable'] = True
    return json_safe(record)


@router.post('/optimizations')
async def start_optimization(req: OptimizationStart, background_tasks: BackgroundTasks, config=Depends(get_config)):
    global _active_id
    with optimization_lock:
        ensure_idle(config)
        caps = capabilities(req.strategy, config)
        if not caps['available']:
            raise HTTPException(422, caps['unavailable_reason'])
        if caps['schema']['revision'] != req.revision:
            raise HTTPException(409, 'Mã đã thay đổi. Tải lại trước khi tối ưu.')
        selected = set(req.spaces)
        allowed = {row['id'] for row in caps['spaces'] if row['enabled']}
        if len(selected) != len(req.spaces) or not selected <= allowed:
            raise HTTPException(422, 'Có nhóm tham số không hỗ trợ hoặc đang bị cấu hình cố định.')
        if req.loss not in {row['id'] for row in caps['losses']}:
            raise HTTPException(422, 'Chỉ dùng hàm mục tiêu chính thức của engine 2026.9.')
        train, oos = ranges(req)
        # No await before reserving native state: API event-loop launchers cannot interleave.
        p, base = freeze(Manifest(strategy=req.strategy, revision=req.revision,
                                  settings=req.settings, preset_id=req.preset_id), config)
        destination = optimization_root(config) / base['id']
        p.rename(destination)
        p = destination
        frozen = json.loads((p / 'inputs.json').read_text())
        runtime = deepcopy(frozen['config'])
        runtime.update(timerange=train, dry_run=True, disableparamexport=True,
                       user_data_dir=str(p / 'inputs'), datadir=str(p / 'inputs/data'),
                       strategy_path=str(p / 'inputs/strategies'), recursive_strategy_search=False)
        normalize_cli_numbers(runtime)
        (p / 'inputs/hyperopt_results').mkdir()
        (p / 'runtime.json').write_text(json.dumps(runtime, ensure_ascii=False), encoding='utf-8')
        record = {k: base[k] for k in ('id', 'strategy', 'revision', 'created_at', 'settings', 'engine',
                                      'input_manifest_sha256', 'input_files', 'input_bytes')}
        record.update(status='prepared', epochs=req.epochs, completed_epochs=0, spaces=req.spaces,
                      loss=req.loss, random_state=req.random_state, min_trades=req.min_trades,
                      workers=req.workers, validation=req.validation, train_timerange=train,
                      oos_timerange=oos, schema=caps['schema'], preset=base.get('preset'),
                      best_epoch=None, error=None, result_sha256=None,
                      runtime_sha256=digest(p / 'runtime.json'),
                      note='Hyperopt native chỉ dùng tập học. Ngoài mẫu phải chạy kiểm định riêng; chưa đổi strategy/paper.')
        try:
            ensure_idle(config)
        except HTTPException:
            record.update(status='failed', finished_at=now(), error='Một tác vụ nghiên cứu khác vừa nhận engine; chưa chạy tối ưu.')
            write_check(p / 'record.json', record)
            raise
        _active_id = record['id']
        ApiBG.analysis_running = True
        process = None
        try:
            write_check(p / 'record.json', record)
            with (p / 'native.log').open('ab') as log:
                process = subprocess.Popen(native_command(p, record), cwd=p, env=child_environment(),
                                           stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                           start_new_session=True)
            _processes[record['id']] = process
            record.update(status='running', started_at=now(), process_identity=process_identity(process.pid))
            write_check(p / 'record.json', record)
            background_tasks.add_task(finish_process, p, process)
        except Exception:
            if process is not None and process.poll() is None:
                stop_owned_group(process, signal.SIGTERM)
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    stop_owned_group(process, signal.SIGKILL)
                    process.wait()
            release(record['id'])
            record.update(status='failed', finished_at=now(), error='Không khởi động được tiến trình Hyperopt native.')
            write_check(p / 'record.json', record)
            raise HTTPException(503, record['error'])
        return json_safe(record)


@router.get('/optimizations')
def list_optimizations(strategy: str | None = None, config=Depends(get_config)):
    with optimization_lock:
        rows = []
        for path in sorted(optimization_root(config).glob('*/record.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.is_symlink() or path.parent.is_symlink():
                continue
            record = refreshed(path.parent)
            if strategy is None or record['strategy'] == strategy:
                rows.append(record)
        return {'optimizations': rows}


@router.get('/optimizations/{uid}')
def get_optimization(uid: str, config=Depends(get_config)):
    with optimization_lock:
        return refreshed(optimization_path(uid, config))


@router.get('/optimizations/{uid}/epochs')
def list_epochs(uid: str, offset: int = 0, limit: int = 50, sort: Literal['loss', 'epoch'] = 'loss', config=Depends(get_config)):
    if offset < 0 or limit < 1 or limit > 100:
        raise HTTPException(422, 'Trang epoch không hợp lệ; tối đa 100 mục mỗi trang.')
    with optimization_lock:
        p = optimization_path(uid, config)
        record = refreshed(p)
        try:
            rows = [epoch_public(row, record) for row in epoch_rows(p, record, record['status'] in TERMINAL)]
        except Exception as e:
            raise HTTPException(409, 'Không đọc được tệp kết quả Hyperopt đã lưu.') from e
        if sort == 'loss':
            rows.sort(key=lambda row: (not row['eligible'], row['loss'] is None, row['loss'] or 0, row['epoch']))
        else:
            rows.sort(key=lambda row: row['epoch'])
        return {'epochs': rows[offset:offset + limit], 'total': len(rows)}


def stop_owned_group(process, sig):
    try:
        if process.poll() is None and os.getpgid(process.pid) == process.pid:
            os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass  # It exited after poll; never substitute another process or PID.


def complete_cancel(process):
    # Native catches SIGINT and saves completed epochs. Bound cancellation even
    # when a custom strategy does not cooperate, targeting only our child group.
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        stop_owned_group(process, signal.SIGTERM)
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            stop_owned_group(process, signal.SIGKILL)


@router.post('/optimizations/{uid}/cancel')
def cancel_optimization(uid: str, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock:
        p = optimization_path(uid, config)
        record = refreshed(p)
        if record['status'] not in ACTIVE:
            return record
        if record['status'] == 'cancelling':
            return record
        process = _processes.get(uid)
        if process is None or uid != _active_id:
            raise HTTPException(409, 'Không còn handle của phiên tối ưu để dừng an toàn.')
        record.update(status='cancelling', cancel_requested_at=now())
        write_check(p / 'record.json', record)
        stop_owned_group(process, signal.SIGINT)
        background_tasks.add_task(complete_cancel, process)
        return json_safe(record)


def chosen_epoch(p, record, epoch):
    if record['status'] not in {'success', 'cancelled'}:
        raise HTTPException(409, 'Chờ phiên tối ưu hoàn tất trước khi dùng một epoch.')
    verified_inputs(p, record)
    try:
        row = next((r for r in epoch_rows(p, record, True) if r['current_epoch'] == epoch), None)
    except Exception as e:
        raise HTTPException(409, 'Kết quả Hyperopt đã thay đổi hoặc không còn hợp lệ.') from e
    if row is None:
        raise HTTPException(404, 'Không có epoch này.')
    if not epoch_public(row, record)['eligible']:
        raise HTTPException(422, 'Epoch chưa đủ số lệnh hoặc mục tiêu không hữu hạn; chưa thể sử dụng.')
    return row


def epoch_values(row, schema):
    from freqtrade.misc import deep_merge_dicts
    combined = deep_merge_dicts(deepcopy(row['params_details']), deepcopy(row['params_not_optimized']))
    allowed = {field['space']: {f['name'] for f in schema['fields'] if f['space'] == field['space']}
               for field in schema['fields']}
    allowed.update(roi=None, stoploss={'stoploss'}, max_open_trades={'max_open_trades'},
                   trailing={'trailing_stop', 'trailing_stop_positive', 'trailing_stop_positive_offset',
                             'trailing_only_offset_is_reached'})
    for group, members in combined.items():
        if group not in allowed or not isinstance(members, dict):
            raise HTTPException(422, 'Epoch có nhóm tham số chưa được hỗ trợ.')
        for name, value in members.items():
            if ((allowed[group] is not None and name not in allowed[group])
                    or (group == 'roi' and not re.fullmatch(r'\d+', name))
                    or not (value is None or type(value) in (str, bool, int) or (type(value) is float and math.isfinite(value)))):
                raise HTTPException(422, 'Epoch chứa giá trị tham số không hợp lệ.')
    try:
        values = {field['name']: combined[field['space']][field['name']]
                  for field in schema['fields'] if field['load']}
    except KeyError as e:
        raise HTTPException(422, 'Epoch thiếu tham số để nạp lại chính xác.') from e
    validate_values(values, schema['fields'])
    return values


class EpochPreset(BaseModel):
    label: str = Field(min_length=1, max_length=70)


@router.post('/optimizations/{uid}/epochs/{epoch}/preset')
def promote_epoch(uid: str, epoch: int, req: EpochPreset, config=Depends(get_config)):
    with optimization_lock, preset_lock:
        ensure_idle(config)
        p = optimization_path(uid, config)
        record = refreshed(p)
        row = chosen_epoch(p, record, epoch)
        for group in set(record['spaces']) & set(BUILTINS):
            if any(key in config and config[key] is not None for key in BUILTINS[group][1]):
                raise HTTPException(409, 'Cấu hình hiện tại đã cố định nhóm ' + group + '; chưa lưu ứng viên sẽ bị ghi đè khi nạp.')
        schema = inspect_parameters(record['strategy'], config)
        if any(schema[k] != record['schema'][k] for k in ('revision', 'schema_revision', 'parameter_revision')):
            raise HTTPException(409, 'Mã hoặc tham số gốc đã đổi. Epoch vẫn có thể kiểm định từ bản đóng băng, nhưng chưa lưu cho thư viện hiện tại.')
        values = epoch_values(row, schema)
        if not req.label.strip():
            raise HTTPException(422, 'Đặt tên cho bộ tham số.')
        folder = preset_root(record['strategy'], config) / uuid4().hex
        folder.mkdir()
        from freqtrade.optimize.hyperopt_tools import HyperoptTools
        HyperoptTools.export_params(row, record['strategy'], folder / 'params.json')
        result = {'id': folder.name, 'strategy': record['strategy'], 'label': req.label.strip(),
                  'revision': schema['revision'], 'schema_revision': schema['schema_revision'],
                  'parameter_revision': schema['parameter_revision'], 'values': values,
                  'created_at': now(), 'native_sha256': sha(folder / 'params.json'),
                  'optimization': {'id': uid, 'epoch': epoch, 'result_sha256': record['result_sha256'],
                                   'spaces': record['spaces'], 'loss': record['loss'],
                                   'train_timerange': record['train_timerange'], 'oos_timerange': record.get('oos_timerange')},
                  'special_params': {k: v for k, v in row['params_details'].items() if k in BUILTINS}}
        write_check(folder / 'record.json', result)
        return result


class EpochValidation(BaseModel):
    mode: Literal['train', 'oos']


@router.post('/optimizations/{uid}/epochs/{epoch}/validate')
async def validate_epoch(uid: str, epoch: int, req: EpochValidation, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with optimization_lock:
        ensure_idle(config)
        source = optimization_path(uid, config)
        original = refreshed(source)
        row = chosen_epoch(source, original, epoch)
        frozen = verified_inputs(source, original)
        timerange = original['train_timerange'] if req.mode == 'train' else original.get('oos_timerange')
        if not timerange:
            raise HTTPException(422, 'Phiên này chưa tách tập kiểm định ngoài mẫu.')
        epoch_values(row, original['schema'])
        p = run_root(config) / uuid4().hex
        (p / 'inputs').mkdir(parents=True)
        (p / 'output').mkdir()
        for name in frozen['files']:
            out = p / name
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, out)
            if digest(out) != frozen['files'][name]:
                raise HTTPException(409, 'Đầu vào thay đổi trong lúc chuẩn bị kiểm định.')
        # Exact private source/data; only replace the chosen parameter JSON and
        # requested train/OOS range. Never merge today's library/default config.
        from freqtrade.optimize.hyperopt_tools import HyperoptTools
        parameter = p / 'inputs/strategies' / (original['strategy'] + '.json')
        HyperoptTools.export_params(row, original['strategy'], parameter)
        new = deepcopy(frozen)
        new.update(id=p.name, created_at=now())
        origin = {'id': uid, 'epoch': epoch, 'mode': req.mode, 'result_sha256': original['result_sha256'],
                  'spaces': original['spaces'], 'loss': original['loss'],
                  'train_timerange': original['train_timerange'], 'oos_timerange': original.get('oos_timerange')}
        new['optimization'] = origin
        new['settings']['timerange'] = timerange
        new['config']['timerange'] = timerange
        new['files'][parameter.relative_to(p).as_posix()] = digest(parameter)
        (p / 'inputs/config.json').write_text(json.dumps(new['config'], indent=2, ensure_ascii=False), encoding='utf-8')
        new['files']['inputs/config.json'] = digest(p / 'inputs/config.json')
        new.pop('preset', None)
        (p / 'inputs.json').write_text(json.dumps(new, indent=2, ensure_ascii=False), encoding='utf-8')
        record = {k: new[k] for k in ('id', 'strategy', 'revision', 'settings', 'engine', 'created_at')}
        record.update(status='prepared', preflight_id=None, input_manifest_sha256=digest(p / 'inputs.json'),
                      input_files=len(new['files']), input_bytes=sum((p / name).stat().st_size for name in new['files']),
                      error=None, filename=None, native_run_id=None, artifact_sha256=None,
                      optimization=origin)
        write_check(p / 'record.json', record)
        from freqtrade.enums import RunMode
        runtime = deepcopy(new['config'])
        runtime.update(runmode=RunMode.BACKTEST, internals={}, verbosity=0, config_files=[])
        return await launch_snapshot(p, record, background_tasks, config, runtime)
