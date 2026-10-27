"""Freeze local research inputs, delegate to Freqtrade, retain verifiable artifacts.

No trading or custom fill logic. Native result archives remain readable by FreqUI.
"""
import base64
import binascii
import hashlib
from io import BytesIO
import json
import re
import shutil
import stat
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile, ZIP_DEFLATED

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
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
    # Hold the same data lock used by the repair promoter from preflight
    # through the complete file snapshot. Per-file hashes alone cannot prevent
    # a mixed-generation snapshot if repair replaces two files between copies.
    from freqtrade.rpc.api_server.api_data_quality import data_source_lock
    with data_source_lock:
        return _freeze_locked(req, config)


def _freeze_locked(req, config):
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
        if digest(out) != digest(params):raise HTTPException(409, 'Tệp tham số đang thay đổi. Tải lại trước khi chạy.')
    selected = inputs / 'strategies' / (req.strategy + '.py')
    if digest(selected) != req.revision:
        raise HTTPException(409, 'Mã đã đổi khi chuẩn bị. Tải lại trước khi chạy.')
    preset = None
    if req.preset_id:
        from freqtrade.rpc.api_server.api_presets import apply_preset
        preset = apply_preset(req.strategy, req.preset_id, inputs, config)
        parameter = inputs / 'strategies' / (req.strategy+'.json')
        inventory[parameter.relative_to(p).as_posix()] = digest(parameter)
    public = reproducible_config(config, req.settings, req.strategy)
    (inputs / 'config.json').write_text(json.dumps(public, indent=2, ensure_ascii=False), encoding='utf-8')
    inventory['inputs/config.json'] = digest(inputs / 'config.json')
    frozen = {'schema': 1, 'id': uid, 'strategy': req.strategy, 'revision': req.revision,
              'settings': req.settings, 'config': public, 'files': inventory,
              'engine': '2026.9', 'created_at': datetime.now(timezone.utc).isoformat(),
              'note': 'Bản sao mã Python local, parameter của chiến lược và toàn bộ feather local. Không đóng băng mạng Binance hoặc thư viện ngoài image.'}
    if preset:frozen['preset'] = preset
    (p / 'inputs.json').write_text(json.dumps(frozen, indent=2, ensure_ascii=False), encoding='utf-8')
    record = {k: frozen[k] for k in ('id', 'strategy', 'revision', 'settings', 'engine', 'created_at')}
    if preset:record['preset'] = preset
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
            parameter_name = 'inputs/strategies/'+record['strategy']+'.json'
            if parameter_name in frozen['files']:
                embedded_params = native.read(f'{output.stem}_{record["strategy"]}.json')
                if hashlib.sha256(embedded_params).hexdigest() != frozen['files'][parameter_name]:
                    raise ValueError('Tham số trong kết quả native khác bản sao đầu vào.')
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
    if record['status'] == 'success' and record.get('replay_of'):
        from freqtrade.rpc.api_server.api_replay import compare_replay
        record['replay_comparison'] = compare_replay(record, config)
    write_check(p / 'record.json', record)


@router.post('/runs')
async def start_run(req: Manifest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    if ApiBG.analysis_running:
        raise HTTPException(409, 'Engine đang chạy một tác vụ. Chờ hoàn tất trước khi chạy tiếp.')
    p, record = freeze(req, config)
    return await launch_snapshot(p, record, background_tasks, config, deepcopy(config))


async def launch_snapshot(p, record, background_tasks, config, runtime):
    """Shared native launcher; replay supplies its archived configuration, never live defaults."""
    from freqtrade.rpc.api_server.api_data_quality import guard_research
    guard_research(config)
    from freqtrade.rpc.api_server.api_backtest import api_start_backtest, api_delete_backtest
    from freqtrade.rpc.api_server.api_schemas import BacktestRequest
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    if ApiBG.analysis_running:
        raise HTTPException(409, 'Engine đang chạy một tác vụ. Chờ hoàn tất trước khi chạy tiếp.')
    frozen = json.loads((p / 'inputs.json').read_text(encoding='utf-8'))
    runtime.update(user_data_dir=p / 'inputs', datadir=p / 'inputs/data',
                   strategy_path=str(p / 'inputs/strategies'), recursive_strategy_search=False,
                   exportdirectory=p / 'output' / ('backtest-result-freqpilot-' + record['id'] + '.json'),
                   export='trades', original_config=deepcopy(frozen['config']))
    # Reset via the official API so a previous run cannot donate cached data to this snapshot.
    api_delete_backtest()
    clear_local_imports(config)
    try:
        await api_start_backtest(BacktestRequest(strategy=record['strategy'], **record['settings'], backtest_cache='none'), background_tasks, runtime)
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


class ImportArtifactRequest(BaseModel):
    archive_base64: str = Field(min_length=16, max_length=90_000_000)
    expected_sha256: str | None = Field(default=None, pattern=r'^[0-9a-fA-F]{64}$')
    install_strategy_if_missing: bool = False

@router.post('/runs/import')
def import_artifact(req: ImportArtifactRequest, config=Depends(get_config)):
    from freqtrade.rpc.api_server.api_local_strategies import NAME
    from freqtrade.rpc.api_server.api_replay import validate_saved_config
    raw_b64 = req.archive_base64.strip()
    if ',' in raw_b64 and raw_b64.split(',', 1)[0].startswith('data:'):
        raw_b64 = raw_b64.split(',', 1)[1].strip()
    try:
        archive_bytes = base64.b64decode(raw_b64, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, 'Tệp gói hồ sơ base64 không hợp lệ.') from error
    if len(archive_bytes) > 64 * 1024 * 1024:
        raise HTTPException(422, 'Gói hồ sơ vượt quá giới hạn 64 MB.')
    actual_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    if req.expected_sha256 and actual_sha256 != req.expected_sha256.lower():
        raise HTTPException(409, 'Dấu vân tay SHA256 của gói tải lên không khớp giá trị kỳ vọng.')
    try:
        with ZipFile(BytesIO(archive_bytes)) as bundle:
            infos = bundle.infolist()
            names = [i.filename for i in infos]
            if len(names) != len(set(names)):
                raise HTTPException(409, 'Gói có tên tệp trùng.')
            if sum(i.file_size for i in infos) > 256 * 1024 * 1024:
                raise HTTPException(422, 'Kích thước giải nén của gói vượt giới hạn an toàn.')
            for info in infos:
                parts = PurePosixPath(info.filename).parts
                if (info.is_dir() or stat.S_ISLNK(info.external_attr >> 16)
                        or PurePosixPath(info.filename).is_absolute() or '..' in parts
                        or '\\' in info.filename or ':' in info.filename):
                    raise HTTPException(409, 'Gói chứa đường dẫn hoặc liên kết không an toàn.')
            manifest_bytes = bundle.read('inputs.json')
            input_manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
            frozen = json.loads(manifest_bytes.decode('utf-8'))
            uid = str(frozen.get('id') or '')
            strategy = str(frozen.get('strategy') or '')
            revision = str(frozen.get('revision') or '')
            files = frozen.get('files')
            settings = frozen.get('settings')
            if (frozen.get('schema') != 1 or frozen.get('engine') != '2026.9'
                    or not re.fullmatch(r'[0-9a-f]{32}', uid)
                    or not NAME.fullmatch(strategy)
                    or not re.fullmatch(r'[0-9a-f]{64}', revision)
                    or not isinstance(files, dict) or not isinstance(settings, dict)):
                raise HTTPException(409, 'Manifest của gói không hợp lệ hoặc khác phiên bản engine 2026.9.')
            dest_dir = run_root(config) / uid
            if dest_dir.exists():
                if (dest_dir / 'record.json').is_file() and verify_run(uid, config)['valid']:
                    existing = json.loads((dest_dir / 'record.json').read_text(encoding='utf-8'))
                    if existing.get('artifact_sha256') == actual_sha256:
                        return existing
                raise HTTPException(409, 'Hồ sơ cùng ID đã tồn tại với nội dung khác. Không ghi đè hồ sơ cũ.')
            required = {'inputs/config.json', f'inputs/strategies/{strategy}.py'}
            if not required.issubset(files):
                raise HTTPException(409, 'Gói thiếu cấu hình hoặc mã chiến lược.')
            for name, expected_hash in files.items():
                parts = PurePosixPath(name).parts
                allowed = (name == 'inputs/config.json' or
                           (len(parts) >= 3 and parts[:2] == ('inputs', 'strategies') and
                            (name.endswith('.py') or name == f'inputs/strategies/{strategy}.json')) or
                           (len(parts) >= 3 and parts[:2] == ('inputs', 'data') and name.endswith('.feather')))
                if not allowed or not re.fullmatch(r'[0-9a-f]{64}', str(expected_hash)):
                    raise HTTPException(409, 'Gói có danh mục tệp đầu vào không hợp lệ.')
                if hashlib.sha256(bundle.read(name)).hexdigest() != expected_hash:
                    raise HTTPException(409, f'Đầu vào trong gói không khớp hash: {name}')
            saved_config = json.loads(bundle.read('inputs/config.json').decode('utf-8'))
            if saved_config != frozen.get('config') or files[f'inputs/strategies/{strategy}.py'] != revision:
                raise HTTPException(409, 'Cấu hình hoặc mã chiến lược không khớp manifest của gói.')
            validate_saved_config(saved_config, frozen)
            output_zips = [n for n in names if n.startswith('output/') and n.endswith('.zip') and len(PurePosixPath(n).parts) == 2]
            output_metas = [n for n in names if n.startswith('output/') and n.endswith('.meta.json') and len(PurePosixPath(n).parts) == 2]
            if len(output_zips) != 1 or len(output_metas) != 1 or output_metas[0] != output_zips[0][:-4] + '.meta.json':
                raise HTTPException(409, 'Gói phải chứa đúng một cặp ZIP và meta kết quả native.')
            expected_members = {'inputs.json', *files.keys(), output_zips[0], output_metas[0]}
            if set(names) != expected_members:
                raise HTTPException(409, 'Gói chứa tệp lạ ngoài danh mục đã kiểm chứng.')
            stem = PurePosixPath(output_zips[0]).stem
            if not re.fullmatch(r'[A-Za-z0-9._-]+', stem):
                raise HTTPException(409, 'Tên tệp kết quả native không hợp lệ.')
            output_zip_bytes = bundle.read(output_zips[0])
            output_meta_bytes = bundle.read(output_metas[0])
            with ZipFile(BytesIO(output_zip_bytes)) as native:
                embedded_py = native.read(f'{stem}_{strategy}.py')
                if hashlib.sha256(embedded_py).hexdigest() != revision:
                    raise HTTPException(409, 'Mã trong kết quả native không khớp revision của gói.')
                param_key = f'inputs/strategies/{strategy}.json'
                if param_key in files:
                    embedded_param = native.read(f'{stem}_{strategy}.json')
                    if hashlib.sha256(embedded_param).hexdigest() != files[param_key]:
                        raise HTTPException(409, 'Tham số trong kết quả native không khớp bản lưu trong gói.')
                stats = json.loads(native.read(f'{stem}.json').decode('utf-8'))['strategy'][strategy]
            metadata = json.loads(output_meta_bytes.decode('utf-8'))[strategy]
            native_run_id = metadata['run_id']
            history = Path(config['user_data_dir']) / 'backtest_results'
            history.mkdir(exist_ok=True)
            hist_zip = history / f'{stem}.zip'
            hist_meta = history / f'{stem}.meta.json'
            if hist_zip.exists() and digest(hist_zip) != hashlib.sha256(output_zip_bytes).hexdigest():
                raise HTTPException(409, 'Tệp kết quả native cùng tên đã tồn tại với nội dung khác.')
            if hist_meta.exists() and digest(hist_meta) != hashlib.sha256(output_meta_bytes).hexdigest():
                raise HTTPException(409, 'Tệp meta native cùng tên đã tồn tại với nội dung khác.')

            dest_dir.mkdir(parents=False)
            (dest_dir / 'output').mkdir()
            (dest_dir / 'artifact.zip').write_bytes(archive_bytes)
            (dest_dir / 'inputs.json').write_bytes(manifest_bytes)
            for name in files:
                out_path = dest_dir / name
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(bundle.read(name))
            (dest_dir / output_zips[0]).write_bytes(output_zip_bytes)
            (dest_dir / output_metas[0]).write_bytes(output_meta_bytes)
            if not hist_zip.exists():
                hist_zip.write_bytes(output_zip_bytes)
            if not hist_meta.exists():
                hist_meta.write_bytes(output_meta_bytes)
            if req.install_strategy_if_missing:
                lib_py = root(config) / f'{strategy}.py'
                if not lib_py.exists() and not lib_py.is_symlink():
                    with lib_py.open('xb') as stream:
                        stream.write(bundle.read(f'inputs/strategies/{strategy}.py'))
            record = {
                'id': uid,
                'strategy': strategy,
                'revision': revision,
                'settings': settings,
                'engine': '2026.9',
                'created_at': str(frozen.get('created_at') or datetime.now(timezone.utc).isoformat()),
                'imported_at': datetime.now(timezone.utc).isoformat(),
                'status': 'success',
                'preflight_id': None,
                'input_manifest_sha256': input_manifest_sha256,
                'input_files': len(files),
                'input_bytes': sum((dest_dir / n).stat().st_size for n in files),
                'error': None,
                'filename': stem,
                'native_run_id': native_run_id,
                'artifact_sha256': actual_sha256,
                'summary': {
                    k: stats.get(k)
                    for k in (
                        'total_trades',
                        'profit_total_abs',
                        'profit_total',
                        'max_drawdown_account',
                        'profit_factor',
                        'wins',
                        'losses',
                        'backtest_start',
                        'backtest_end',
                        'timeframe',
                    )
                },
            }
            if frozen.get('preset'):
                record['preset'] = frozen['preset']
            if frozen.get('replay_of'):
                record['replay_of'] = frozen['replay_of']
            write_check(dest_dir / 'record.json', record)
            return record
    except HTTPException:
        raise
    except (BadZipFile, KeyError, ValueError, TypeError, OSError) as error:
        raise HTTPException(409, 'Không đọc được gói hồ sơ hợp lệ. Chưa nhập gói.') from error
