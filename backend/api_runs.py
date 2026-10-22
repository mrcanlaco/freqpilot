"""Freeze local research inputs, delegate to Freqtrade, retain verifiable artifacts.

No trading or custom fill logic. Native result archives remain readable by FreqUI.
"""
import hashlib
import json
import re
import shutil
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import root, target, read
from freqtrade.rpc.api_server.api_studio import Manifest, manifest, storage, write_check, json_safe

router = APIRouter()


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def run_root(config):
    p = storage(config) / 'runs'
    p.mkdir(exist_ok=True)
    return p


def run_path(uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(422, 'Mã hồ sơ không hợp lệ.')
    p = run_root(config) / uid
    if p.is_symlink() or not (p / 'record.json').is_file():
        raise HTTPException(404, 'Không có hồ sơ này.')
    return p


def reproducible_config(config, settings, name):
    # Explicit allowlist: no API credentials, webhooks, exchange keys or config-file paths.
    fields = ('dry_run', 'trading_mode', 'margin_mode', 'stake_currency', 'stake_amount',
              'max_open_trades', 'dry_run_wallet', 'tradable_balance_ratio', 'fiat_display_currency',
              'fee', 'timeframe', 'timeframe_detail', 'unfilledtimeout', 'entry_pricing',
              'exit_pricing', 'order_types', 'order_time_in_force', 'pairlists',
              'dataformat_ohlcv', 'dataformat_trades', 'liquidation_buffer',
              'minimal_roi', 'stoploss', 'trailing_stop', 'trailing_stop_positive',
              'trailing_stop_positive_offset', 'trailing_only_offset_is_reached',
              'use_exit_signal', 'exit_profit_only', 'exit_profit_offset', 'ignore_roi_if_entry_signal')
    result = {k: deepcopy(config[k]) for k in fields if k in config}
    result.update(settings, strategy=name, dry_run=True, backtest_cache='none')
    result['exchange'] = {k: deepcopy(config['exchange'][k]) for k in
                          ('name', 'pair_whitelist', 'pair_blacklist') if k in config['exchange']}
    return json_safe(result)


def clear_local_imports(config):
    # Official API resets its candle cache but Python keeps imported helper modules.
    # This research-only service must import helpers from the new snapshot as well.
    paths = (root(config), run_root(config))
    for name, module in list(sys.modules.items()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        try:
            source = Path(filename).resolve()
            if any(source.is_relative_to(base) for base in paths):
                sys.modules.pop(name, None)
        except (TypeError, OSError):
            continue


def freeze(req, config):
    prepared = manifest(req, config)
    uid = uuid4().hex
    p = run_root(config) / uid
    inputs = p / 'inputs'
    (inputs / 'strategies').mkdir(parents=True)
    (inputs / 'data').mkdir()
    (p / 'output').mkdir()
    inventory = {}
    source_root = root(config)
    data_root = Path(config['datadir']).resolve()
    for base, dest, pattern in [(source_root, inputs / 'strategies', '*.py'),
                                (data_root, inputs / 'data', '*.feather')]:
        for src in sorted(base.rglob(pattern)):
            if '__pycache__' in src.parts:
                continue
            if src.is_symlink() or not src.resolve().is_relative_to(base):
                raise HTTPException(422, 'Không đóng gói tệp liên kết bên ngoài thư viện.')
            out = dest / src.relative_to(base)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, out)
            # Reject a file changed concurrently while the snapshot was being made.
            copied = digest(out)
            if copied != digest(src):
                raise HTTPException(409, 'Mã hoặc dữ liệu đang thay đổi. Thử lại khi tải dữ liệu đã xong.')
            inventory[out.relative_to(p).as_posix()] = copied
    params = target(req.strategy, config).with_suffix('.json')
    if params.exists():
        if params.is_symlink():
            raise HTTPException(422, 'Không đóng gói parameter liên kết.')
        out = inputs / 'strategies' / params.name
        shutil.copyfile(params, out)
        inventory[out.relative_to(p).as_posix()] = digest(out)
    selected = inputs / 'strategies' / (req.strategy + '.py')
    if digest(selected) != req.revision:
        raise HTTPException(409, 'Mã đã đổi khi chuẩn bị. Tải lại trước khi chạy.')
    public = reproducible_config(config, req.settings, req.strategy)
    (inputs / 'config.json').write_text(json.dumps(public, indent=2, ensure_ascii=False), encoding='utf-8')
    inventory['inputs/config.json'] = digest(inputs / 'config.json')
    frozen = {'schema': 1, 'id': uid, 'strategy': req.strategy, 'revision': req.revision,
              'settings': req.settings, 'config': public, 'files': inventory,
              'engine': '2026.9', 'created_at': datetime.now(timezone.utc).isoformat(),
              'note': 'Bản sao mã Python local, parameter của chiến lược và toàn bộ feather local. Không đóng băng mạng Binance hoặc thư viện ngoài image.'}
    (p / 'inputs.json').write_text(json.dumps(frozen, indent=2, ensure_ascii=False), encoding='utf-8')
    record = {k: frozen[k] for k in ('id', 'strategy', 'revision', 'settings', 'engine', 'created_at')}
    record.update(status='prepared', preflight_id=prepared['id'], input_manifest_sha256=digest(p / 'inputs.json'),
                  input_files=len(inventory), input_bytes=sum((p / name).stat().st_size for name in inventory),
                  error=None, filename=None, native_run_id=None, artifact_sha256=None)
    write_check(p / 'record.json', record)
    return p, record


def finish(uid, config):
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    p = run_path(uid, config)
    record = json.loads((p / 'record.json').read_text(encoding='utf-8'))
    job = ApiBG.jobs.get(record.get('job_id'))
    try:
        if not job or job['status'] != 'success':
            raise ValueError((job or {}).get('error') or 'Backtest không hoàn tất.')
        files = list((p / 'output').glob('*.zip'))
        if len(files) != 1:
            raise ValueError('Engine chưa xuất đúng một ZIP kết quả. Không gắn kết quả khác vào hồ sơ.')
        output = files[0]
        frozen = json.loads((p / 'inputs.json').read_text(encoding='utf-8'))
        if digest(p / 'inputs.json') != record['input_manifest_sha256']:
            raise ValueError('Hồ sơ đầu vào đã thay đổi.')
        for name, expected in frozen['files'].items():
            if digest(p / name) != expected:
                raise ValueError('Bản sao đầu vào đã đổi: ' + name)
        with ZipFile(output) as native:
            embedded = native.read(f'{output.stem}_{record["strategy"]}.py')
            if hashlib.sha256(embedded).hexdigest() != record['revision']:
                raise ValueError('Mã trong kết quả native khác bản sao đầu vào.')
            stats = json.loads(native.read(output.stem + '.json'))['strategy'][record['strategy']]
        meta = output.with_suffix('.meta.json')
        metadata = json.loads(meta.read_text())[record['strategy']]
        record.update(filename=output.stem, native_run_id=metadata['run_id'],
                      summary={k: stats.get(k) for k in ('total_trades', 'profit_total_abs', 'profit_total',
                                'max_drawdown_account', 'profit_factor', 'wins', 'losses',
                                'backtest_start', 'backtest_end', 'timeframe')})
        # Retain the original archive and inputs as one exclusive, verifiable package.
        with ZipFile(p / 'artifact.zip', 'x', ZIP_DEFLATED) as bundle:
            for name in ['inputs.json', *frozen['files'], output.relative_to(p).as_posix(), meta.relative_to(p).as_posix()]:
                bundle.write(p / name, name)
        record['artifact_sha256'] = digest(p / 'artifact.zip')
        history = Path(config['user_data_dir']) / 'backtest_results'
        history.mkdir(exist_ok=True)
        for src in (output, meta):
            with (history / src.name).open('xb') as stream, src.open('rb') as source:
                shutil.copyfileobj(source, stream)
        record['status'] = 'success'
    except Exception as error:
        record.update(status='failed', error=str(error))
    record['finished_at'] = datetime.now(timezone.utc).isoformat()
    write_check(p / 'record.json', record)


@router.post('/runs')
async def start_run(req: Manifest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    from freqtrade.rpc.api_server.api_backtest import api_start_backtest, api_delete_backtest
    from freqtrade.rpc.api_server.api_schemas import BacktestRequest
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    if ApiBG.analysis_running:
        raise HTTPException(409, 'Engine đang chạy một tác vụ. Chờ hoàn tất trước khi chạy tiếp.')
    p, record = freeze(req, config)
    runtime = deepcopy(config)
    runtime.update(user_data_dir=p / 'inputs', datadir=p / 'inputs/data',
                   strategy_path=str(p / 'inputs/strategies'), recursive_strategy_search=False,
                   exportdirectory=p / 'output' / ('backtest-result-freqpilot-' + record['id'] + '.json'),
                   export='trades', original_config=reproducible_config(config, req.settings, req.strategy))
    # Reset via the official API so a previous run cannot donate cached data to this snapshot.
    api_delete_backtest()
    clear_local_imports(config)
    try:
        await api_start_backtest(BacktestRequest(strategy=req.strategy, **req.settings, backtest_cache='none'), background_tasks, runtime)
        record.update(status='running', job_id=ApiBG.bt['job_id'])
        write_check(p / 'record.json', record)
        background_tasks.add_task(finish, record['id'], config)
    except Exception as error:
        record.update(status='failed', error=str(error))
        write_check(p / 'record.json', record)
        raise
    return record


@router.get('/runs')
def list_runs(strategy: str | None = None, config=Depends(get_config)):
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    if strategy:
        target(strategy, config)
    records = []
    for file in sorted(run_root(config).glob('*/record.json'), key=lambda x: x.stat().st_mtime, reverse=True):
        record = json.loads(file.read_text(encoding='utf-8'))
        if strategy and record['strategy'] != strategy:
            continue
        if record['status'] == 'running' and record.get('job_id') not in ApiBG.jobs:
            record.update(status='interrupted', error='Dịch vụ đã khởi động lại. Hồ sơ không được tự chạy lại.')
            write_check(file, record)
        records.append(record)
        if len(records) >= 100:
            break
    return {'runs': records}


@router.get('/runs/{uid}/verify')
def verify_run(uid: str, config=Depends(get_config)):
    p = run_path(uid, config)
    record = json.loads((p / 'record.json').read_text(encoding='utf-8'))
    if record['status'] != 'success':
        raise HTTPException(409, 'Chỉ kiểm tra gói đã hoàn tất.')
    actual = digest(p / 'artifact.zip') if (p / 'artifact.zip').is_file() else None
    manifest_ok = digest(p / 'inputs.json') == record['input_manifest_sha256']
    return {'id': uid, 'valid': actual == record['artifact_sha256'] and manifest_ok,
            'artifact_sha256': actual, 'expected_sha256': record['artifact_sha256'],
            'input_manifest_valid': manifest_ok,
            'note': 'Kiểm tra tính toàn vẹn bản lưu, không chứng nhận chiến lược có lợi nhuận.'}


@router.get('/runs/{uid}/source')
def run_source(uid: str, config=Depends(get_config)):
    p = run_path(uid, config)
    record = json.loads((p / 'record.json').read_text(encoding='utf-8'))
    if not verify_run(uid, config)['valid']:
        raise HTTPException(409, 'Gói đã thay đổi. Không hiển thị mã như một bản lưu hợp lệ.')
    with ZipFile(p / 'artifact.zip') as bundle:
        content = bundle.read('inputs/strategies/' + record['strategy'] + '.py').decode('utf-8-sig')
    return {'content': content,
            'revision': record['revision'], 'strategy': record['strategy']}


@router.get('/runs/{uid}/artifact')
def download_artifact(uid: str, config=Depends(get_config)):
    if not verify_run(uid, config)['valid']:
        raise HTTPException(409, 'Gói đã thay đổi hoặc thiếu tệp. Không tải gói sai hash.')
    return FileResponse(run_path(uid, config) / 'artifact.zip', media_type='application/zip', filename=f'freqpilot-{uid}.zip')
