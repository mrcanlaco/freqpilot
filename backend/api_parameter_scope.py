"""Native, sequential multi-seed Hyperopt experiments over frozen research inputs.

The official 2026.9 CLI accepts selected spaces and a seed, but no per-Parameter
bounds override.  This adapter deliberately does not rewrite strategy source or
monkeypatch the engine to pretend that it does.
"""
import json
import re
import shutil
import signal
import subprocess
import threading
from copy import deepcopy
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import root as strategy_root
from freqtrade.rpc.api_server.api_studio import Manifest, storage, write_check, json_safe
from freqtrade.rpc.api_server.api_runs import digest, freeze
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
from freqtrade.rpc.api_server import api_optimization as opt

router = APIRouter()
_lock = threading.RLock()
_active_id: str | None = None
_owned: dict[str, subprocess.Popen] = {}
MAX_COPY_BYTES = 6 * 1024**3


class SeedExperimentRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    strategy: str
    revision: str
    preset_id: str | None = None
    settings: dict
    epochs: int = Field(default=30, ge=1, le=250)
    spaces: list[str] = Field(min_length=1, max_length=20)
    loss: str = 'SharpeHyperOptLossDaily'
    min_trades: int = Field(default=10, ge=1, le=10000)
    workers: int = Field(default=1, ge=1, le=2)
    seeds: list[int] = Field(min_length=2, max_length=5)


def _folder(config):
    p = storage(config) / 'seed_experiments'
    p.mkdir(exist_ok=True)
    return p


def _path(uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(422, 'Mã thí nghiệm seed không hợp lệ.')
    p = _folder(config) / uid
    if p.is_symlink() or (p / 'record.json').is_symlink() or not (p / 'record.json').is_file():
        raise HTTPException(404, 'Không có thí nghiệm seed này.')
    return p


def _native_identity_alive(p, record):
    identity = record.get('active_process_identity')
    command = record.get('active_command')
    if not identity or not command or opt.process_identity(identity['pid']) != identity:
        return False
    try:
        observed = (Path('/proc') / str(identity['pid']) / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')
        return observed == command
    except (OSError, UnicodeError):
        return True  # uncertain identity must still block a competing native task


def guard_seed_orphans(config):
    """Call from native research guards as well as this module's own starts."""
    with _lock:
        for file in _folder(config).glob('*/record.json'):
            if file.is_symlink() or file.parent.is_symlink():
                continue
            try:
                record = json.loads(file.read_text())
            except (OSError, ValueError):
                raise HTTPException(409, 'Không đọc được hồ sơ seed cũ; dừng nhận tác vụ nghiên cứu mới.')
            if record.get('status') in {'prepared', 'running', 'cancelling', 'interrupted'} and _native_identity_alive(file.parent, record):
                raise HTTPException(409, 'Còn tiến trình Hyperopt seed từ phiên trước; chưa thể nhận tác vụ engine mới.')


def _validate(req, config):
    if len(set(req.seeds)) != len(req.seeds) or any(type(seed) is not int or seed < 1 or seed > 2147483647 for seed in req.seeds):
        raise HTTPException(422, 'Chọn 2–5 seed dương, khác nhau.')
    if req.epochs * len(req.seeds) > 500:
        raise HTTPException(422, 'Tổng ngân sách tối đa 500 epoch.')
    caps = opt.capabilities(req.strategy, config)
    if not caps['available']:
        raise HTTPException(422, caps['unavailable_reason'])
    if caps['schema']['revision'] != req.revision:
        raise HTTPException(409, 'Mã chiến lược đã đổi. Tải lại trước khi tối ưu.')
    allowed = {space['id'] for space in caps['spaces'] if space['enabled']}
    if len(set(req.spaces)) != len(req.spaces) or not set(req.spaces) <= allowed:
        raise HTTPException(422, 'Có nhóm tham số không hỗ trợ hoặc đang bị cố định.')
    if req.loss not in {loss['id'] for loss in caps['losses']}:
        raise HTTPException(422, 'Chỉ dùng hàm mục tiêu native 2026.9.')
    one = opt.OptimizationStart(strategy=req.strategy, revision=req.revision,
                                preset_id=req.preset_id, settings=req.settings,
                                epochs=req.epochs, spaces=req.spaces, loss=req.loss,
                                random_state=req.seeds[0], min_trades=req.min_trades,
                                workers=req.workers, validation='single')
    train, _ = opt.ranges(one)
    return caps, train


def _source_bytes(config):
    paths = list(strategy_root(config).rglob('*.py')) + list(Path(config['datadir']).rglob('*.feather'))
    if any(path.is_symlink() for path in paths):
        raise HTTPException(422, 'Không dùng tệp dữ liệu/mã liên kết ngoài thư viện.')
    return sum(path.stat().st_size for path in paths)


@router.get('/optimization-parameter-scope/{strategy}')
def parameter_scope(strategy: str, config=Depends(get_config)):
    with opt.optimization_lock:
        caps = opt.capabilities(strategy, config)
        return {'strategy': strategy, 'engine': '2026.9',
                'revision': caps['schema']['revision'],
                'parameter_revision': caps['schema']['parameter_revision'],
                'native_spaces': caps['spaces'],
                'parameters': caps['schema']['fields'],
                'per_parameter_override': {
                    'available': False,
                    'reason': 'Hyperopt CLI 2026.9 chỉ nhận --spaces theo nhóm; phạm vi low/high lấy từ Parameter trong mã chiến lược. Không sửa mã hoặc monkeypatch engine để đổi riêng từng khoảng.',
                    'safe_action': 'Chỉnh định nghĩa Parameter như một revision chiến lược mới, rồi chạy lại trên snapshot mới.'},
                'multi_seed': {'available': True, 'method': 'Các child Hyperopt native chạy tuần tự, mỗi child có --random-state riêng trên cùng input đóng băng.'}}


@router.post('/seed-experiments/preview')
def preview(req: SeedExperimentRequest, config=Depends(get_config)):
    with opt.optimization_lock, _lock:
        _, train = _validate(req, config)
        estimate = _source_bytes(config) * (len(req.seeds) + 1)
        if estimate > MAX_COPY_BYTES:
            raise HTTPException(422, 'Dự kiến bản sao đầu vào vượt ngân sách 6 GiB.')
        return {'strategy': req.strategy, 'revision': req.revision, 'train_timerange': train,
                'seeds': req.seeds, 'epochs_each': req.epochs,
                'total_epochs': req.epochs * len(req.seeds), 'workers_each': req.workers,
                'estimated_input_bytes': estimate,
                'selection_rule': 'Chỉ so sánh loss/metric trên train; không dùng OOS để chọn lại seed.',
                'note': 'Xem trước không chạy và chưa chứng nhận dữ liệu; lúc bắt đầu sẽ kiểm tra rồi đóng băng dữ liệu.'}


def _persist(p, record):
    write_check(p / 'record.json', record)


def _reserve(uid):
    global _active_id
    _active_id = uid
    opt._active_id = 'seed:' + uid
    ApiBG.analysis_running = True


def _release(uid):
    global _active_id
    _owned.pop(uid, None)
    if _active_id == uid:
        _active_id = None
        if opt._active_id == 'seed:' + uid:
            opt._active_id = None
        ApiBG.analysis_running = False


@router.post('/seed-experiments')
def start(req: SeedExperimentRequest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    with opt.optimization_lock, _lock:
        opt.ensure_idle(config)
        guard_seed_orphans(config)
        caps, train = _validate(req, config)
        estimate = _source_bytes(config) * (len(req.seeds) + 1)
        if estimate > MAX_COPY_BYTES:
            raise HTTPException(422, 'Dự kiến bản sao đầu vào vượt ngân sách 6 GiB.')
        p, base = freeze(Manifest(strategy=req.strategy, revision=req.revision,
                                  settings=req.settings, preset_id=req.preset_id), config)
        dest = _folder(config) / base['id']
        p.rename(dest)
        p = dest
        if base['input_bytes'] * (len(req.seeds) + 1) > MAX_COPY_BYTES:
            record = {'id': p.name, 'strategy': req.strategy, 'status': 'failed',
                      'error': 'Bản sao thực tế vượt ngân sách 6 GiB.', 'created_at': opt.now()}
            _persist(p, record)
            raise HTTPException(422, record['error'])
        record = {key: base[key] for key in ('id', 'strategy', 'revision', 'engine', 'created_at',
                                             'settings', 'input_manifest_sha256', 'input_files', 'input_bytes')}
        record.update(status='prepared', train_timerange=train,
                      seeds=req.seeds, epochs_each=req.epochs, total_epochs=req.epochs * len(req.seeds),
                      spaces=req.spaces, loss=req.loss, min_trades=req.min_trades,
                      workers=req.workers, preset=base.get('preset'),
                      schema_revision=caps['schema']['schema_revision'],
                      results=[], completed_seeds=0, current_seed=None,
                      active_process_identity=None, active_command=None,
                      cancel_requested_at=None, error=None,
                      selection_rule='Chỉ so sánh loss/metric trên train; không dùng OOS để chọn lại seed.',
                      estimated_input_bytes=base['input_bytes'] * (len(req.seeds) + 1),
                      note='Chỉ đánh giá train; không tự áp dụng ứng viên, không chạm paper.')
        _persist(p, record)
        _reserve(p.name)
        background_tasks.add_task(_run, p)
        return json_safe(record)


def _verified_snapshot(p, record):
    base = p / 'inputs.json'
    if base.is_symlink() or digest(base) != record['input_manifest_sha256']:
        raise ValueError('Manifest đầu vào seed đã thay đổi.')
    frozen = json.loads(base.read_text())
    for name, expected in frozen['files'].items():
        member = Path(name)
        full = p / member
        if member.is_absolute() or '..' in member.parts or member.parts[0] != 'inputs' or full.is_symlink() or digest(full) != expected:
            raise ValueError('Bản sao đầu vào seed đã thay đổi: ' + name)
    return frozen


def _clone(p, seed, frozen):
    child = p / 'children' / str(seed)
    (child / 'inputs').mkdir(parents=True)
    for name, expected in frozen['files'].items():
        out = child / name
        out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p / name, out)
        if digest(out) != expected:
            raise ValueError('Bản sao child không khớp hash: ' + name)
    (child / 'inputs/hyperopt_results').mkdir()
    return child


def _verify_child(child, frozen):
    for name, expected in frozen['files'].items():
        member = child / name
        if member.is_symlink() or digest(member) != expected:
            raise ValueError('Input child thay đổi trong khi chạy: ' + name)


def _cancelled(p, record):
    disk = json.loads((p / 'record.json').read_text())
    if disk.get('cancel_requested_at'):
        record['cancel_requested_at'] = disk['cancel_requested_at']
        record['status'] = 'cancelling'
    return bool(record.get('cancel_requested_at'))


def _run(p):
    uid = p.name
    record = json.loads((p / 'record.json').read_text())
    try:
        frozen = _verified_snapshot(p, record)
        record['status'] = 'running'
        _persist(p, record)
        for seed in record['seeds']:
            with opt.optimization_lock, _lock:
                if _cancelled(p, record):
                    break
                child = _clone(p, seed, frozen)
                runtime = deepcopy(frozen['config'])
                runtime.update(timerange=record['train_timerange'], dry_run=True,
                               disableparamexport=True, user_data_dir=str(child / 'inputs'),
                               datadir=str(child / 'inputs/data'),
                               strategy_path=str(child / 'inputs/strategies'),
                               recursive_strategy_search=False)
                opt.normalize_cli_numbers(runtime)
                (child / 'runtime.json').write_text(json.dumps(runtime, ensure_ascii=False), encoding='utf-8')
                local = {'strategy': record['strategy'], 'epochs': record['epochs_each'],
                         'spaces': record['spaces'], 'loss': record['loss'],
                         'random_state': seed, 'workers': record['workers'],
                         'min_trades': record['min_trades']}
                command = opt.native_command(child, local)
                record.update(current_seed=seed, active_command=command,
                              current_stage='hyperopt', status='running')
                _persist(p, record)
                with (child / 'native.log').open('ab') as log:
                    process = subprocess.Popen(command, cwd=child,
                                               env=opt.child_environment(),
                                               stdin=subprocess.DEVNULL,
                                               stdout=log, stderr=subprocess.STDOUT,
                                               start_new_session=True)
                _owned[uid] = process
                record['active_process_identity'] = opt.process_identity(process.pid)
                _persist(p, record)
            process.wait()
            with opt.optimization_lock, _lock:
                _owned.pop(uid, None)
                record['active_process_identity'] = None
                record['active_command'] = None
                _cancelled(p, record)
                result = {'seed': seed, 'status': 'failed',
                          'runtime_sha256': digest(child / 'runtime.json'),
                          'completed_epochs': 0, 'eligible_epochs': 0,
                          'best_epoch': None, 'result_sha256': None}
                try:
                    _verify_child(child, frozen)
                    rows = opt.epoch_rows(child, local, terminal=process.returncode == 0)
                    public = [opt.epoch_public(row, local) for row in rows]
                    eligible = [row for row in public if row['eligible']]
                    file = opt.result_file(child, local)
                    result.update(completed_epochs=len(rows), eligible_epochs=len(eligible),
                                  best_epoch=min(eligible, key=lambda row: (row['loss'], row['epoch'])) if eligible else None,
                                  result_sha256=digest(file) if file else None,
                                  status='cancelled' if record.get('cancel_requested_at') else
                                         'success' if process.returncode == 0 and rows else 'failed')
                except Exception:
                    result['error'] = 'Không xác minh được kết quả native của seed này.'
                record['results'].append(result)
                record['completed_seeds'] += 1
                record['current_seed'] = None
                _persist(p, record)
        _verified_snapshot(p, record)
        ranked = [row for row in record['results']
                  if row['status'] == 'success' and row['best_epoch'] is not None]
        ranked.sort(key=lambda row: (row['best_epoch']['loss'], row['seed']))
        record['train_ranking'] = [
            {'seed': row['seed'], 'loss': row['best_epoch']['loss'],
             'epoch': row['best_epoch']['epoch'], 'metrics': row['best_epoch']['metrics']}
            for row in ranked]
        record.update(status='cancelled' if _cancelled(p, record) else 'success',
                      research_status='review' if all(row['status'] == 'success' for row in record['results'])
                      and len(record['results']) == len(record['seeds']) else 'incomplete',
                      finished_at=opt.now(), current_stage=None)
        _persist(p, record)
    except Exception:
        record.update(status='failed', research_status='incomplete',
                      error='Không hoàn tất thí nghiệm seed; kiểm tra nhật ký cục bộ.',
                      finished_at=opt.now(), current_stage=None)
        _persist(p, record)
    finally:
        with opt.optimization_lock, _lock:
            _release(uid)


def _refreshed(p):
    record = json.loads((p / 'record.json').read_text())
    if record['status'] in {'prepared', 'running', 'cancelling'} and record['id'] not in _owned and _active_id != record['id']:
        record.update(status='interrupted', research_status='incomplete',
                      orphan_process_alive=_native_identity_alive(p, record),
                      finished_at=opt.now(),
                      error='Dịch vụ khởi động lại; mất handle của child, không tự chạy tiếp.')
        _persist(p, record)
    elif record['status'] == 'interrupted' and record.get('orphan_process_alive'):
        if not _native_identity_alive(p, record):
            record['orphan_process_alive'] = False
            _persist(p, record)
    return json_safe(record)


@router.get('/seed-experiments')
def list_experiments(strategy: str | None = None, config=Depends(get_config)):
    with _lock:
        rows = []
        for path in sorted(_folder(config).glob('*/record.json'), key=lambda p: p.stat().st_mtime, reverse=True):
            if path.is_symlink() or path.parent.is_symlink():
                continue
            row = _refreshed(path.parent)
            if strategy is None or row['strategy'] == strategy:
                rows.append(row)
        return {'experiments': rows}


@router.get('/seed-experiments/{uid}')
def get_experiment(uid: str, config=Depends(get_config)):
    with _lock:
        return _refreshed(_path(uid, config))


@router.post('/seed-experiments/{uid}/cancel')
def cancel(uid: str, config=Depends(get_config)):
    with opt.optimization_lock, _lock:
        p = _path(uid, config)
        record = _refreshed(p)
        if record['status'] not in {'prepared', 'running', 'cancelling'}:
            return record
        process = _owned.get(uid)
        if _active_id != uid:
            raise HTTPException(409, 'Không còn quyền sở hữu child để dừng an toàn.')
        record['cancel_requested_at'] = opt.now()
        record['status'] = 'cancelling'
        _persist(p, record)
        if process is not None:
            opt.stop_owned_group(process, signal.SIGINT)
        return json_safe(record)
