"""Rerun an owned frozen package through the official backtester, without restoring the library."""
import hashlib
import json
import math
import re
import shutil
import stat
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import PurePosixPath
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import NAME
from freqtrade.rpc.api_server.api_runs import digest, launch_snapshot, run_path, run_root, verify_run
from freqtrade.rpc.api_server.api_studio import write_check

router = APIRouter()
NOTICE = ('Dùng mã, tham số, nến/mark/funding và cấu hình trong gói. Metadata thị trường Binance '
          'vẫn được engine lấy qua mạng; gói cũ chưa ghim phần này nên không bảo đảm kết quả khớp. '
          'Không sửa thư viện, tải thêm nến hoặc đổi paper.')


@contextmanager
def checked_bundle(uid, config, expected=None):
    p = run_path(uid, config)
    record = json.loads((p / 'record.json').read_text(encoding='utf-8'))
    if not verify_run(uid, config)['valid'] or (expected and expected != record['artifact_sha256']):
        raise HTTPException(409, 'Gói đã thay đổi hoặc khác bản đã xem. Kiểm tra lại trước khi chạy.')
    if not NAME.fullmatch(record['strategy']) or record.get('engine') != '2026.9':
        raise HTTPException(409, 'Chiến lược hoặc phiên bản engine trong gói không được hỗ trợ.')
    try:
        with (p / 'artifact.zip').open('rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != record['artifact_sha256']:
                raise HTTPException(409, 'Gói thay đổi trong khi đọc.')
            stream.seek(0)
            with ZipFile(stream) as bundle:
                names = bundle.namelist()
                if len(names) != len(set(names)):
                    raise HTTPException(409, 'Gói có tên tệp trùng.')
                manifest_bytes = bundle.read('inputs.json')
                if hashlib.sha256(manifest_bytes).hexdigest() != record['input_manifest_sha256']:
                    raise HTTPException(409, 'Manifest trong gói không khớp bản lưu.')
                frozen = json.loads(manifest_bytes)
                if (frozen.get('id') != uid or frozen.get('strategy') != record['strategy']
                        or frozen.get('revision') != record['revision'] or frozen.get('engine') != '2026.9'
                        or frozen.get('settings') != record['settings']):
                    raise HTTPException(409, 'Ngữ cảnh gói không khớp hồ sơ.')
                files = frozen['files']
                required = {'inputs/config.json', 'inputs/strategies/' + record['strategy'] + '.py'}
                if not required.issubset(files):
                    raise HTTPException(409, 'Gói thiếu cấu hình hoặc mã chiến lược.')
                for name, expected_hash in files.items():
                    parts = PurePosixPath(name).parts
                    allowed = (name == 'inputs/config.json' or
                               (len(parts) >= 3 and parts[:2] == ('inputs', 'strategies') and
                                (name.endswith('.py') or name == 'inputs/strategies/'+record['strategy']+'.json')) or
                               (len(parts) >= 3 and parts[:2] == ('inputs', 'data') and name.endswith('.feather')))
                    if (not allowed or PurePosixPath(name).is_absolute() or '..' in parts or '\\' in name
                            or ':' in name or not re.fullmatch('[0-9a-f]{64}', expected_hash)):
                        raise HTTPException(409, 'Gói có đường dẫn hoặc dấu vân tay đầu vào không hợp lệ.')
                    info = bundle.getinfo(name)
                    if info.is_dir() or stat.S_ISLNK(info.external_attr >> 16):
                        raise HTTPException(409, 'Gói chứa tệp liên kết hoặc thư mục thay cho đầu vào.')
                    with bundle.open(info) as source:
                        if hashlib.file_digest(source, 'sha256').hexdigest() != expected_hash:
                            raise HTTPException(409, 'Đầu vào trong gói không khớp: '+name)
                saved_config = json.loads(bundle.read('inputs/config.json'))
                if saved_config != frozen['config']:
                    raise HTTPException(409, 'Hai bản cấu hình trong gói khác nhau.')
                source_key = 'inputs/strategies/' + record['strategy'] + '.py'
                if files[source_key] != record['revision']:
                    raise HTTPException(409, 'Mã gốc không khớp revision hồ sơ.')
                validate_saved_config(saved_config, record)
                yield bundle, frozen, record
    except (BadZipFile, KeyError, ValueError, TypeError, OSError) as error:
        raise HTTPException(409, 'Không đọc được gói đầu vào hoàn chỉnh. Chưa chạy backtest.') from error


def validate_saved_config(cfg, record):
    from freqtrade.rpc.api_server.api_runs import reproducible_config
    from freqtrade.rpc.api_server.api_schemas import BacktestRequest
    ex = cfg.get('exchange', {})
    if (cfg.get('dry_run') is not True or cfg.get('trading_mode') != 'futures'
            or cfg.get('margin_mode') != 'isolated' or cfg.get('stake_currency') != 'USDT'
            or ex.get('name') != 'binance' or not ex.get('pair_whitelist')
            or not set(ex['pair_whitelist']).issubset({'BTC/USDT:USDT', 'ETH/USDT:USDT'})
            or cfg.get('fee') is None or cfg.get('pairlists') != [{'method': 'StaticPairList'}]):
        raise HTTPException(409, 'Chỉ chạy lại gói Binance BTC/ETH Futures isolated, phí rõ ràng và StaticPairList.')
    allowed = {'timerange', 'timeframe', 'timeframe_detail', 'dry_run_wallet', 'max_open_trades', 'stake_amount', 'enable_protections'}
    if set(record['settings']) - allowed or cfg != reproducible_config(cfg, record['settings'], record['strategy']):
        raise HTTPException(409, 'Gói có cấu hình ngoài phạm vi nghiên cứu đã lưu.')
    BacktestRequest(strategy=record['strategy'], **record['settings'], backtest_cache='none')


@router.get('/runs/{uid}/replay')
def replay_preview(uid: str, config=Depends(get_config)):
    with checked_bundle(uid, config) as (_, frozen, record):
        cfg = frozen['config']
        return {'id': uid, 'strategy': record['strategy'], 'revision': record['revision'],
                'artifact_sha256': record['artifact_sha256'], 'settings': record['settings'],
                'preset': frozen.get('preset'), 'pairs': cfg['exchange']['pair_whitelist'],
                'fee': cfg['fee'], 'input_files': len(frozen['files']),
                'input_bytes': record['input_bytes'], 'engine': record['engine'], 'note': NOTICE}


class ReplayRequest(BaseModel):
    artifact_sha256: str = Field(pattern='^[0-9a-f]{64}$')


@router.post('/runs/{uid}/replay')
async def replay_run(uid: str, req: ReplayRequest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    from freqtrade.enums import RunMode
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    if ApiBG.analysis_running:
        raise HTTPException(409, 'Engine đang chạy một tác vụ. Chờ hoàn tất trước khi chạy lại.')
    with checked_bundle(uid, config, req.artifact_sha256) as (bundle, frozen, original):
        new_id = uuid4().hex
        p = run_root(config) / new_id
        (p / 'output').mkdir(parents=True)
        for name, expected in frozen['files'].items():
            out = p / name
            out.parent.mkdir(parents=True, exist_ok=True)
            with bundle.open(name) as source, out.open('xb') as dest:
                shutil.copyfileobj(source, dest)
            if digest(out) != expected:
                raise HTTPException(409, 'Gói thay đổi khi sao chép. Chưa chạy backtest.')
        frozen = deepcopy(frozen)
        frozen.update(id=new_id, created_at=datetime.now(timezone.utc).isoformat(),
                      replay_of={'id': uid, 'artifact_sha256': original['artifact_sha256']})
        write_check(p / 'inputs.json', frozen)
        record = {k: frozen[k] for k in ('id', 'strategy', 'revision', 'settings', 'engine', 'created_at', 'replay_of')}
        if frozen.get('preset'): record['preset'] = frozen['preset']
        record.update(status='prepared', preflight_id=None, input_manifest_sha256=digest(p / 'inputs.json'),
                      input_files=len(frozen['files']), input_bytes=sum((p / name).stat().st_size for name in frozen['files']),
                      error=None, filename=None, native_run_id=None, artifact_sha256=None)
        write_check(p / 'record.json', record)
    # Do not merge the current service configuration or environment overrides into the recipe.
    runtime = deepcopy(frozen['config'])
    runtime.update(runmode=RunMode.BACKTEST, internals={}, verbosity=0, config_files=[])
    return await launch_snapshot(p, record, background_tasks, config, runtime)


def native_stats(p, record):
    with ZipFile(p / 'output' / (record['filename'] + '.zip')) as archive:
        result = json.loads(archive.read(record['filename']+'.json'))['strategy'][record['strategy']]
    if not isinstance(result.get('trades'), list) or result.get('total_trades') != len(result['trades']):
        raise ValueError('Native trades missing or incomplete')
    return result


def require_finite(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError('Nonfinite native comparison value')
    if isinstance(value, dict):
        for child in value.values(): require_finite(child)
    if isinstance(value, list):
        for child in value: require_finite(child)


def compare_replay(record, config):
    try:
        origin = record['replay_of']
        with checked_bundle(origin['id'], config, origin['artifact_sha256']) as (bundle, _, source):
            name = 'output/'+source['filename']+'.zip'
            # Stream the original native archive through a temporary seekable handle, bounded by disk.
            import tempfile
            with tempfile.TemporaryFile() as stream:
                with bundle.open(name) as member: shutil.copyfileobj(member, stream)
                stream.seek(0)
                with ZipFile(stream) as native:
                    before = json.loads(native.read(source['filename']+'.json'))['strategy'][source['strategy']]
        after = native_stats(run_path(record['id'], config), record)
        if not isinstance(before.get('trades'), list) or before.get('total_trades') != len(before['trades']):
            raise ValueError('Source native trades incomplete')
        metrics = ('total_trades', 'profit_total_abs', 'profit_total', 'max_drawdown_account',
                   'starting_balance', 'final_balance', 'backtest_start', 'backtest_end', 'timeframe')
        if any(k not in before or k not in after for k in metrics):
            raise ValueError('Native summary incomplete')
        for result in (before, after):
            require_finite([result['trades'], {key: result[key] for key in metrics}])
        different_metrics = [k for k in metrics if before[k] != after[k]]
        different_trades = sum(x != y for x, y in zip(before['trades'], after['trades'])) + abs(len(before['trades'])-len(after['trades']))
        return {'status': 'matched' if not different_metrics and not different_trades else 'different',
                'source_id': origin['id'], 'source_trades': len(before['trades']), 'replayed_trades': len(after['trades']),
                'different_trades': different_trades, 'different_metrics': different_metrics,
                'comparison': 'Exact equality of every native trade field (including orders/fees/funding), list order and selected summary metrics; no rounding or tolerance.',
                'note': NOTICE}
    except Exception:
        return {'status': 'unavailable', 'source_id': record['replay_of']['id'],
                'note': 'Backtest mới đã lưu, nhưng gói gốc hoặc kết quả native không còn đủ để đối chiếu. Không xác nhận khớp.'}
