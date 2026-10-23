"""Audited futures data coverage and explicit, bounded native data repair.

Only the webserver's research datadir is ever promoted.  Existing backtest
snapshots are immutable and paper workers are outside this module's ownership.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import pandas as pd
import requests
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict

from freqtrade.data.history import get_datahandler
from freqtrade.enums import CandleType
from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG

from freqtrade.rpc.api_server.api_studio import storage


router = APIRouter()
VERSION = '2026-10-data-quality-1'
MAX_DAYS = 730
REPAIR_MAX_DAYS = 120
PREVIEW_LIFETIME = timedelta(minutes=15)
ISSUE_LIMIT = 30
FUNDING_URL = 'https://fapi.binance.com/fapi/v1/fundingRate'
EXCHANGE_INFO_URL = 'https://fapi.binance.com/fapi/v1/exchangeInfo'
FUNDING_TIME_TOLERANCE_MS = 10  # Observed Binance +4/+6 ms vs native whole-second timestamp
_lock = threading.RLock()
# Shared with freeze(): readers hold this across *all* feather copies.  A
# repair may download and validate privately without it, then holds it only
# for the short multi-file promotion/rollback section.
data_source_lock = threading.RLock()
_active_job: str | None = None
_ALLOWED_PAIRS = {'BTC/USDT:USDT', 'ETH/USDT:USDT'}
_ALLOWED_FRAMES = {'1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '1d'}
_SEVERITY = {'invalid': 3, 'missing': 2, 'unknown': 1, 'ok': 0}


class FundingEventConflict(ValueError):
    """Distinct funding rows are too close to match without ambiguity."""


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str), encoding='utf-8')
    os.replace(tmp, path)


def _hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _root(config) -> Path:
    p = storage(config) / 'data_quality'
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bounds(timerange: str) -> tuple[datetime, datetime]:
    if not re.fullmatch(r'\d{8}-\d{8}', timerange):
        raise HTTPException(422, 'Chọn ngày bắt đầu và kết thúc UTC dạng YYYYMMDD-YYYYMMDD.')
    try:
        start = datetime.strptime(timerange[:8], '%Y%m%d').replace(tzinfo=timezone.utc)
        end = datetime.strptime(timerange[9:], '%Y%m%d').replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise HTTPException(422, 'Ngày UTC không hợp lệ.') from exc
    if start >= end or end - start > timedelta(days=MAX_DAYS):
        raise HTTPException(422, f'Khoảng phải lớn hơn 0 và tối đa {MAX_DAYS} ngày.')
    if end > utcnow() + timedelta(days=1):
        raise HTTPException(422, 'Không thể kiểm tra dữ liệu tương lai.')
    return start, end


def _frame_seconds(frame: str) -> int:
    if frame not in _ALLOWED_FRAMES:
        raise HTTPException(422, 'Khung nến chưa hỗ trợ trong trang Dữ liệu.')
    amount, unit = int(frame[:-1]), frame[-1]
    return amount * {'m': 60, 'h': 3600, 'd': 86400}[unit]


def _request(config, timerange, timeframe, detail_timeframe, warmup_candles) -> dict:
    start, end = _bounds(timerange)
    _frame_seconds(timeframe)
    _frame_seconds(detail_timeframe)
    if not 0 <= warmup_candles <= 10000:
        raise HTTPException(422, 'Warmup cần từ 0 đến 10.000 nến.')
    if config.get('exchange', {}).get('name', '').lower() != 'binance':
        raise HTTPException(422, 'Trang này dành cho dữ liệu Binance Futures của bộ nghiên cứu.')
    mode = config.get('trading_mode')
    if mode is not None and getattr(mode, 'value', mode) != 'futures':
        raise HTTPException(422, 'Chỉ kiểm tra dữ liệu Binance Futures ở trang này.')
    pairs = list(dict.fromkeys(config.get('exchange', {}).get('pair_whitelist', [])))
    if not pairs or any(pair not in _ALLOWED_PAIRS for pair in pairs):
        raise HTTPException(422, 'Chỉ hỗ trợ BTC/ETH Binance USDT-M Futures đã cấu hình.')
    return {'timerange': timerange, 'timeframe': timeframe, 'detail_timeframe': detail_timeframe,
            'warmup_candles': warmup_candles, 'pairs': pairs,
            'start': start.isoformat(), 'end': end.isoformat()}


def _specs(request):
    for pair in request['pairs']:
        yield pair, request['timeframe'], 'futures'
        if request['detail_timeframe'] != request['timeframe']:
            yield pair, request['detail_timeframe'], 'futures'
        yield pair, '1h', 'mark'
        yield pair, '1h', 'funding_rate'


def _file(config, pair, frame, kind) -> Path:
    datadir = Path(config['datadir']).resolve()
    handler = get_datahandler(datadir, config.get('dataformat_ohlcv', 'feather'))
    candle = CandleType(kind)
    path = handler._pair_data_filename(datadir, pair, frame, candle_type=candle)
    if path.is_symlink() or not path.resolve().is_relative_to(datadir):
        raise HTTPException(422, 'Đường dẫn dữ liệu nằm ngoài kho nghiên cứu.')
    return path


def _issue(code, severity, message, *, start=None, end=None, count=None):
    out = {'code': code, 'severity': severity, 'message': message}
    if start is not None:
        out['start'] = start.isoformat() if isinstance(start, datetime) else str(start)
    if end is not None:
        out['end'] = end.isoformat() if isinstance(end, datetime) else str(end)
    if count is not None:
        out['count'] = int(count)
    return out


def _status(issues, default='ok'):
    return max((x['severity'] for x in issues), key=lambda x: _SEVERITY[x], default=default)


def _raw_file(config, request, pair, frame, kind):
    path = _file(config, pair, frame, kind)
    start = datetime.fromisoformat(request['start'])
    end = datetime.fromisoformat(request['end'])
    warmup_start = start - timedelta(seconds=_frame_seconds(frame) * request['warmup_candles']) if kind == 'futures' and frame == request['timeframe'] else start
    row = {'pair': pair, 'timeframe': frame, 'type': kind, 'rows': 0, 'start': None, 'end': None,
           'last_closed': None, 'sha256': None, 'status': 'ok', 'issues': [],
           'required_start': warmup_start.isoformat(), 'required_end': end.isoformat(),
           'path': str(path.relative_to(Path(config['datadir']).resolve())).replace('\\', '/')}
    issues = row['issues']
    if not path.is_file():
        issues.append(_issue('file_missing', 'missing', 'Chưa có tệp dữ liệu.', start=warmup_start, end=end))
        row['status'] = 'missing'
        return row
    row['sha256'] = _hash(path)
    try:
        df = pd.read_feather(path)
    except Exception:
        issues.append(_issue('file_unreadable', 'invalid', 'Không đọc được tệp Feather.'))
        row['status'] = 'invalid'
        return row
    row['rows'] = len(df)
    required_cols = {'date', 'funding_rate'} if kind == 'funding_rate' else {'date', 'open', 'high', 'low', 'close', 'volume'}
    if not required_cols.issubset(df.columns):
        issues.append(_issue('columns_missing', 'invalid', 'Thiếu cột dữ liệu bắt buộc.'))
        row['status'] = 'invalid'
        return row
    if df.empty:
        issues.append(_issue('empty', 'missing', 'Tệp dữ liệu trống.', start=warmup_start, end=end))
        row['status'] = 'missing'
        return row
    dates = pd.to_datetime(df['date'], utc=True, errors='coerce')
    if dates.isna().any():
        issues.append(_issue('timestamp_invalid', 'invalid', 'Có timestamp không hợp lệ.', count=dates.isna().sum()))
        row['status'] = 'invalid'
        return row
    if dates.duplicated().any():
        issues.append(_issue('timestamp_duplicate', 'invalid', 'Có timestamp trùng.', count=dates.duplicated().sum()))
    if not dates.is_monotonic_increasing:
        issues.append(_issue('timestamp_unsorted', 'invalid', 'Timestamp chưa tăng dần.'))
    first, last = dates.min().to_pydatetime(), dates.max().to_pydatetime()
    row['start'], row['end'] = first.isoformat(), last.isoformat()
    if kind != 'funding_rate':
        step = timedelta(seconds=_frame_seconds(frame))
        row['last_closed'] = (last + step).isoformat() if last + step <= utcnow() else None
        numeric = df[['open', 'high', 'low', 'close', 'volume']].apply(pd.to_numeric, errors='coerce')
        finite = numeric.notna().all(axis=1) & numeric.apply(lambda col: col.map(math.isfinite)).all(axis=1)
        if not finite.all():
            issues.append(_issue('nonfinite', 'invalid', 'Có giá hoặc khối lượng không hữu hạn.', count=(~finite).sum()))
        o, h, l, c = (numeric[k] for k in ('open', 'high', 'low', 'close'))
        bad_ohlc = (o <= 0) | (h <= 0) | (l <= 0) | (c <= 0) | (h < o) | (h < c) | (l > o) | (l > c) | (h < l)
        if bad_ohlc.any():
            issues.append(_issue('ohlc_invalid', 'invalid', 'Quan hệ OHLC hoặc giá không hợp lệ.', count=bad_ohlc.sum()))
        if kind == 'futures' and (numeric['volume'] < 0).any():
            issues.append(_issue('volume_invalid', 'invalid', 'Khối lượng giao dịch âm.', count=(numeric['volume'] < 0).sum()))
        window = dates[(dates >= warmup_start) & (dates < end)]
        expected_last = end - step
        if first > warmup_start or window.empty or window.iloc[0].to_pydatetime() > warmup_start:
            actual = window.iloc[0].to_pydatetime() if not window.empty else end
            issues.append(_issue('start_missing', 'missing', 'Thiếu dữ liệu ở đầu khoảng hoặc warmup.', start=warmup_start, end=actual))
        if last < expected_last or window.empty or window.iloc[-1].to_pydatetime() < expected_last:
            actual = window.iloc[-1].to_pydatetime() + step if not window.empty else warmup_start
            issues.append(_issue('end_missing', 'missing', 'Thiếu dữ liệu tới ngày kết thúc đã chọn.', start=actual, end=end))
        if len(window) > 1:
            delta = window.diff().iloc[1:]
            gaps = delta > step
            for index in delta[gaps].index[:ISSUE_LIMIT]:
                previous = dates.loc[index - 1] if index - 1 in dates.index else dates.iloc[dates.index.get_loc(index) - 1]
                issues.append(_issue('middle_gap', 'missing', 'Thiếu nến giữa khoảng.', start=previous.to_pydatetime() + step,
                                     end=dates.loc[index].to_pydatetime(), count=delta.loc[index] // step - 1))
            if int(gaps.sum()) > ISSUE_LIMIT:
                issues.append(_issue('more_gaps', 'missing', 'Còn thêm khoảng thiếu chưa hiển thị.', count=int(gaps.sum()) - ISSUE_LIMIT))
            if (delta < step).any():
                issues.append(_issue('timestamp_spacing', 'invalid', 'Khoảng cách timestamp không đúng khung nến.'))
        # Feather may retain millisecond timestamps. Convert units explicitly
        # before checking boundaries in nanoseconds.
        epoch_ns = dates.dt.as_unit('ns').astype('int64')
        if (epoch_ns % int(step.total_seconds() * 1_000_000_000) != 0).any():
            issues.append(_issue('timestamp_alignment', 'invalid', 'Timestamp lệch ranh giới khung nến.'))
    else:
        rates = pd.to_numeric(df['funding_rate'], errors='coerce')
        if not rates.notna().all() or not rates.map(math.isfinite).all():
            issues.append(_issue('funding_nonfinite', 'invalid', 'Funding rate không hữu hạn.'))
        # Funding timestamps are events. There is no fixed 8-hour completeness test.
        if not ((dates >= start) & (dates < end)).any():
            issues.append(_issue('funding_unverified', 'unknown', 'Chưa có sự kiện funding cục bộ trong khoảng; cần đối chiếu Binance.'))
    row['status'] = _status(issues)
    return row


def _binance_events(symbol: str, start: datetime, end: datetime, session=requests):
    cursor, finish = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    events = []
    pages = 0
    while cursor < finish:
        pages += 1
        if pages > 10:
            raise RuntimeError('Vượt giới hạn 10 trang lịch sử funding.')
        response = session.get(FUNDING_URL, params={'symbol': symbol, 'startTime': cursor,
                                                     'endTime': finish - 1, 'limit': 1000}, timeout=12)
        response.raise_for_status()
        batch = response.json()
        if not isinstance(batch, list):
            raise RuntimeError('Binance không trả về danh sách funding.')
        batch = sorted(batch, key=lambda x: int(x['fundingTime']))
        for item in batch:
            stamp = int(item['fundingTime'])
            if cursor <= stamp < finish:
                events.append((stamp, float(item['fundingRate'])))
        if len(batch) < 1000:
            break
        last = int(batch[-1]['fundingTime'])
        if last < cursor:
            raise RuntimeError('Phân trang funding không tiến tới.')
        cursor = last + 1
    events.sort(key=lambda event: event[0])
    if any(right[0] - left[0] <= FUNDING_TIME_TOLERANCE_MS
           for left, right in zip(events, events[1:])):
        raise FundingEventConflict('Binance trả sự kiện funding trùng hoặc sát nhau bất thường.')
    return events, pages


def _compare_funding_events(remote, local, start_ms, end_ms):
    """Monotonic one-to-one matching; never round events into a set/bucket."""
    local = sorted((stamp, rate) for stamp, rate in local
                   if start_ms - FUNDING_TIME_TOLERANCE_MS <= stamp < end_ms + FUNDING_TIME_TOLERANCE_MS)
    if any(right[0] - left[0] <= FUNDING_TIME_TOLERANCE_MS
           for left, right in zip(local, local[1:])):
        raise FundingEventConflict('Tệp cục bộ có sự kiện funding trùng hoặc sát nhau bất thường.')
    remote = sorted(remote)
    missing, extra, changed = [], [], []
    i = j = 0
    while i < len(remote) and j < len(local):
        remote_time, remote_rate = remote[i]
        local_time, local_rate = local[j]
        delta = remote_time - local_time
        if abs(delta) <= FUNDING_TIME_TOLERANCE_MS:
            if not math.isclose(local_rate, remote_rate, rel_tol=0, abs_tol=1e-10):
                changed.append(remote_time)
            i += 1
            j += 1
        elif local_time < remote_time - FUNDING_TIME_TOLERANCE_MS:
            if start_ms <= local_time < end_ms:
                extra.append(local_time)
            j += 1
        else:
            missing.append(remote_time)
            i += 1
    missing.extend(stamp for stamp, _ in remote[i:])
    extra.extend(stamp for stamp, _ in local[j:] if start_ms <= stamp < end_ms)
    return missing, extra, changed


def _verify_funding(config, request, files, session=requests):
    start, end = datetime.fromisoformat(request['start']), datetime.fromisoformat(request['end'])
    result = {'status': 'ok', 'reason': None, 'pairs': [], 'source': FUNDING_URL,
              'time_tolerance_ms': FUNDING_TIME_TOLERANCE_MS,
              'query_start': start.isoformat(), 'query_end_exclusive': end.isoformat(), 'checked_at': utcnow().isoformat()}
    for pair in request['pairs']:
        local_row = next(x for x in files if x['pair'] == pair and x['type'] == 'funding_rate')
        symbol = pair.split('/')[0] + 'USDT'
        item = {'pair': pair, 'symbol': symbol, 'status': 'unknown', 'events_binance': None,
                'events_local': None, 'pages': None, 'issues': []}
        try:
            events, pages = _binance_events(symbol, start, end, session)
            item['pages'], item['events_binance'] = pages, len(events)
            if local_row['sha256'] is None or local_row['status'] == 'invalid':
                item['status'] = 'missing' if local_row['sha256'] is None else 'invalid'
            else:
                df = pd.read_feather(_file(config, pair, '1h', 'funding_rate'))
                dates = pd.to_datetime(df['date'], utc=True)
                local = [(int(t.value // 1_000_000), float(rate))
                         for t, rate in zip(dates, df['funding_rate'])]
                start_ms, end_ms = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
                item['events_local'] = sum(start_ms <= stamp < end_ms for stamp, _ in local)
                absent, extra, changed = _compare_funding_events(events, local, start_ms, end_ms)
                if absent:
                    item['issues'].append(_issue('funding_events_missing', 'missing', 'Thiếu sự kiện funding đã xác nhận trên Binance.', count=len(absent),
                                                  start=datetime.fromtimestamp(absent[0] / 1000, timezone.utc)))
                if extra or changed:
                    item['issues'].append(_issue('funding_events_different', 'invalid', 'Sự kiện hoặc rate funding khác Binance.', count=len(extra) + len(changed)))
                item['status'] = _status(item['issues'])
        except FundingEventConflict:
            item['status'] = 'invalid'
            item['issues'].append(_issue('funding_events_duplicate', 'invalid',
                                         'Có sự kiện funding trùng hoặc sát nhau; không thể ghép duy nhất.'))
        except (requests.RequestException, OSError, RuntimeError, ValueError, TypeError, KeyError) as exc:
            item['status'] = 'unknown'
            item['issues'].append(_issue('funding_api_unavailable', 'unknown', 'Chưa đối chiếu được funding với Binance: ' + type(exc).__name__))
        result['pairs'].append(item)
    result['status'] = max((x['status'] for x in result['pairs']), key=lambda s: _SEVERITY[s], default='unknown')
    if result['status'] == 'unknown':
        result['reason'] = 'Không kết luận đầy đủ funding khi chưa truy vấn được Binance.'
    return result


def _market_metadata(request, session=requests):
    """Current public rules only; never label these as historical rules."""
    result = {'status': 'ok', 'checked_at': utcnow().isoformat(), 'source': EXCHANGE_INFO_URL,
              'historical': False, 'pairs': []}
    for pair in request['pairs']:
        symbol = pair.split('/')[0] + 'USDT'
        item = {'pair': pair, 'symbol': symbol, 'status': 'unknown', 'filters': []}
        try:
            response = session.get(EXCHANGE_INFO_URL, params={'symbol': symbol}, timeout=12)
            response.raise_for_status()
            symbols = response.json()['symbols']
            matching = next(x for x in symbols if x['symbol'] == symbol)
            item['status'] = 'ok'
            item['price_precision'] = matching.get('pricePrecision')
            item['quantity_precision'] = matching.get('quantityPrecision')
            item['filters'] = [{key: value for key, value in f.items()
                                if key in {'filterType', 'tickSize', 'stepSize', 'minQty', 'minNotional', 'notional'}}
                               for f in matching.get('filters', [])
                               if f.get('filterType') in {'PRICE_FILTER', 'LOT_SIZE', 'MIN_NOTIONAL', 'NOTIONAL'}]
        except (requests.RequestException, OSError, ValueError, TypeError, KeyError, StopIteration):
            result['status'] = 'unknown'
        result['pairs'].append(item)
    return result


def quality_report(config, timerange: str, timeframe: str = '15m', detail_timeframe: str = '1m',
                   warmup_candles: int = 200, verify_funding: bool = False, *, session=requests,
                   persist: bool = True) -> dict:
    request = _request(config, timerange, timeframe, detail_timeframe, warmup_candles)
    files = [_raw_file(config, request, *spec) for spec in _specs(request)]
    funding = (_verify_funding(config, request, files, session) if verify_funding else
               {'status': 'unknown', 'reason': 'Chưa yêu cầu đối chiếu lịch sử funding Binance.', 'pairs': [],
                'source': FUNDING_URL, 'checked_at': None})
    for row in files:
        if row['type'] != 'funding_rate':
            continue
        check = next((x for x in funding['pairs'] if x['pair'] == row['pair']), None)
        if check and check['status'] != 'unknown' and row['status'] == 'unknown':
            row['status'] = check['status']
            row['issues'] = [x for x in row['issues'] if x['code'] != 'funding_unverified']
    issues = [{**issue, 'pair': row['pair'], 'timeframe': row['timeframe'], 'type': row['type']}
              for row in files for issue in row['issues']
              if not (verify_funding and issue['code'] == 'funding_unverified'
                      and any(item['pair'] == row['pair'] and item['status'] != 'unknown'
                              for item in funding['pairs']))]
    for pair in funding['pairs']:
        issues.extend({**issue, 'pair': pair['pair'], 'timeframe': '1h', 'type': 'funding_rate'}
                      for issue in pair['issues'])
    status = _status(issues, funding['status'])
    if funding['status'] == 'unknown' and status == 'ok':
        status = 'unknown'
    dataset_sha256 = hashlib.sha256(json.dumps(
        [(x['pair'], x['timeframe'], x['type'], x['sha256']) for x in files],
        separators=(',', ':')).encode()).hexdigest()
    report = {'id': uuid4().hex, 'version': VERSION, 'checked_at': utcnow().isoformat(),
              'status': status, 'request': request, 'files': files, 'issues': issues,
              'funding_verification': funding, 'dataset_sha256': dataset_sha256,
              'exchange_metadata': (_market_metadata(request, session) if verify_funding else
                                    {'status': 'unknown', 'historical': False, 'pairs': [],
                                     'checked_at': None, 'source': EXCHANGE_INFO_URL}),
              'engine_image_digest': config.get('freqpilot_engine_image_digest'),
              'coverage': {'requested_start': request['start'], 'requested_end_exclusive': request['end'],
                           'base_warmup_start': (datetime.fromisoformat(request['start']) -
                                                 timedelta(seconds=_frame_seconds(timeframe) * warmup_candles)).isoformat(),
                           'informative_dependencies': 'unknown'},
              'engine': 'Freqtrade 2026.9',
              'note': 'Dữ liệu thô; funding chỉ khớp Binance khi trạng thái đối chiếu là ok. Snapshot cũ giữ nguyên.'}
    if persist:
        _json(_root(config) / 'audits' / (report['id'] + '.json'), report)
    return report


@router.get('/data-quality')
def get_quality(timerange: str, timeframe: str = '15m', detail_timeframe: str = '1m',
                warmup_candles: int = 200, verify_funding: bool = False, config=Depends(get_config)):
    return quality_report(config, timerange, timeframe, detail_timeframe, warmup_candles, verify_funding)


@router.get('/data-quality/audits/{audit_id}')
def get_quality_audit(audit_id: str, config=Depends(get_config)):
    report = _read_record(config, 'audits', audit_id)
    stale = []
    for row in report['files']:
        path = _file(config, row['pair'], row['timeframe'], row['type'])
        if (_hash(path) if path.is_file() else None) != row['sha256']:
            stale.append({'pair': row['pair'], 'timeframe': row['timeframe'], 'type': row['type']})
    return {**report, 'is_current': not stale, 'stale_files': stale}


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    preview_id: str


def _record_path(config, group, uid):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):
        raise HTTPException(422, 'Mã tác vụ dữ liệu không hợp lệ.')
    return _root(config) / group / (uid + '.json')


def _read_record(config, group, uid):
    path = _record_path(config, group, uid)
    if path.is_symlink() or not path.is_file():
        raise HTTPException(404, 'Không có tác vụ dữ liệu này.')
    return json.loads(path.read_text(encoding='utf-8'))


def _check_preview_sources(config, preview):
    audit = _read_record(config, 'audits', preview['audit_id'])
    for row in audit['files']:
        live = _file(config, row['pair'], row['timeframe'], row['type'])
        if (_hash(live) if live.is_file() else None) != row['sha256']:
            raise HTTPException(409, 'Dữ liệu đã đổi từ khi xem trước; kiểm tra lại.')


def _make_preview(config, report):
    request = report['request']
    start = datetime.fromisoformat(request['start']) - timedelta(seconds=_frame_seconds(request['timeframe']) * request['warmup_candles'])
    end = datetime.fromisoformat(request['end'])
    if end - start > timedelta(days=REPAIR_MAX_DAYS):
        raise HTTPException(422, f'Mỗi lần tải bù tối đa {REPAIR_MAX_DAYS} ngày tính cả warmup; hãy chia khoảng.')
    operations = []
    for row in report['files']:
        if row['status'] in ('missing', 'invalid'):
            operations.append({'pair': row['pair'], 'timeframe': row['timeframe'], 'type': row['type'],
                               'start': row['required_start'], 'end': row['required_end'],
                               'reason': [x['code'] for x in row['issues']], 'before_sha256': row['sha256']})
    # An event-level check may detect a missing/changed funding event despite
    # the local file itself passing syntax/coverage checks.
    for pair in report['funding_verification']['pairs']:
        if pair['status'] in ('missing', 'invalid') and not any(x['pair'] == pair['pair'] and x['type'] == 'funding_rate' for x in operations):
            row = next(x for x in report['files'] if x['pair'] == pair['pair'] and x['type'] == 'funding_rate')
            operations.append({'pair': pair['pair'], 'timeframe': '1h', 'type': 'funding_rate',
                               'start': row['required_start'], 'end': row['required_end'],
                               'reason': [x['code'] for x in pair['issues']], 'before_sha256': row['sha256']})
    id_ = uuid4().hex
    preview = {'id': id_, 'status': 'ready' if operations else 'nothing_to_repair',
               'checked_at': utcnow().isoformat(), 'expires_at': (utcnow() + PREVIEW_LIFETIME).isoformat(),
               'request': request, 'audit_id': report['id'], 'operations': operations,
               'estimated_files': len(operations),
               'estimated_candles': sum(math.ceil((end - datetime.fromisoformat(op['start'])).total_seconds() /
                                                    _frame_seconds(op['timeframe'])) for op in operations if op['type'] != 'funding_rate'),
               'note': 'Tải lại khoảng đã chọn vào vùng riêng bằng Freqtrade 2026.9; kiểm tra trước khi đưa vào kho nghiên cứu. Không động tới paper.'}
    _json(_record_path(config, 'previews', id_), preview)
    return preview


@router.get('/data-repair/preview')
def repair_preview(timerange: str, timeframe: str = '15m', detail_timeframe: str = '1m',
                   warmup_candles: int = 200, verify_funding: bool = False, config=Depends(get_config)):
    report = quality_report(config, timerange, timeframe, detail_timeframe, warmup_candles, verify_funding)
    return _make_preview(config, report)


def repair_active(config=None):
    if _active_job is not None:
        return True
    if config is None:
        return False
    for path in (_root(config) / 'jobs').glob('*.json'):
        if path.is_symlink():
            continue
        record = json.loads(path.read_text(encoding='utf-8'))
        if record['status'] in ('pending', 'running'):
            record.update(status='interrupted', error='Dịch vụ đã khởi động lại; tác vụ không tự chạy tiếp.',
                          finished_at=utcnow().isoformat())
            _json(path, record)
    return False


def guard_research(config=None):
    if repair_active(config):
        raise HTTPException(409, 'Đang tải và xác minh dữ liệu; chờ tác vụ hoàn tất trước khi chạy nghiên cứu.')


def _native_download(config, op, staging):
    from freqtrade.configuration import TimeRange
    from freqtrade.data.history.history_utils import refresh_backtest_ohlcv_data
    from freqtrade.enums import RunMode
    from freqtrade.resolvers.exchange_resolver import ExchangeResolver

    # Build an explicit, credential-free downloader recipe. The native exchange
    # uses public Binance market data and has no reason to see API/JWT secrets.
    private = {key: config[key] for key in ('trading_mode', 'margin_mode', 'stake_currency',
                                            'fee', 'dataformat_ohlcv', 'timeframe') if key in config}
    staging.mkdir(parents=True, exist_ok=True)
    private['exchange'] = {'name': 'binance', 'pair_whitelist': [op['pair']], 'pair_blacklist': []}
    private['dry_run'] = True
    private['runmode'] = RunMode.UTIL_EXCHANGE
    private['datadir'] = staging
    private['user_data_dir'] = staging.parent
    exchange = ExchangeResolver.load_exchange(private, validate=False)
    start = datetime.fromisoformat(op['start']).strftime('%Y%m%d')
    end = datetime.fromisoformat(op['end']).strftime('%Y%m%d')
    missing_pairs = refresh_backtest_ohlcv_data(
        exchange, pairs=[op['pair']], timeframes=[op['timeframe']], datadir=staging,
        trading_mode='futures', timerange=TimeRange.parse_timerange(f'{start}-{end}'),
        erase=True, data_format=config.get('dataformat_ohlcv', 'feather'),
        candle_types=[CandleType(op['type'])], no_parallel_download=True)
    if missing_pairs:
        raise RuntimeError('Binance không có dữ liệu cho cặp đã chọn.')


def _promote_candidate(config, job, op, staging):
    live = _file(config, op['pair'], op['timeframe'], op['type'])
    staged_cfg = {**config, 'datadir': staging}
    staged = _file(staged_cfg, op['pair'], op['timeframe'], op['type'])
    if not staged.is_file():
        raise RuntimeError('Downloader không tạo tệp được yêu cầu.')
    try:
        existing = pd.read_feather(live) if live.is_file() else None
    except Exception:
        existing = None  # a corrupt file cannot contribute trustworthy outside-range data
    fresh = pd.read_feather(staged)
    merged = pd.concat([existing, fresh], ignore_index=True) if existing is not None else fresh
    merged = merged.drop_duplicates(subset=['date'], keep='last').sort_values('date').reset_index(drop=True)
    candidate = staging.parent / 'candidates' / live.name
    candidate.parent.mkdir(parents=True, exist_ok=True)
    merged.to_feather(candidate)
    return live, candidate


def _commit_candidates(config, job_id, preview, candidates, private_root, candidate_report):
    with data_source_lock:
        if ApiBG.analysis_running:
            raise RuntimeError('Có tác vụ native đang sử dụng dữ liệu; chưa thay nguồn.')
        # Every input from the reviewed audit must still match, including files
        # this repair did not modify. Snapshots are excluded by the same lock.
        _check_preview_sources(config, preview)
        candidate_report['promotion_candidate'] = True
        _json(_root(config) / 'audits' / (candidate_report['id'] + '.json'), candidate_report)
        backups = []
        promoted = []
        try:
            for live, candidate in candidates:
                live.parent.mkdir(parents=True, exist_ok=True)
                backup = private_root / 'backups' / live.relative_to(Path(config['datadir']).resolve())
                backup.parent.mkdir(parents=True, exist_ok=True)
                if live.is_file():
                    shutil.copy2(live, backup)
                    backups.append((live, backup))
                temporary = live.with_name(live.name + '.' + job_id + '.tmp')
                shutil.copy2(candidate, temporary)
                os.replace(temporary, live)
                promoted.append(live)
        except Exception:
            for live in reversed(promoted):
                backup = next((b for p, b in backups if p == live), None)
                if backup:
                    os.replace(backup, live)
                elif live.exists():
                    live.unlink()
            raise
        return len(promoted)


def _run_repair(job_id, config):
    global _active_job
    path = _record_path(config, 'jobs', job_id)
    record = _read_record(config, 'jobs', job_id)
    preview = _read_record(config, 'previews', record['preview_id'])
    request = preview['request']
    private_root = _root(config) / 'repairs' / job_id
    staging = private_root / 'data'
    try:
        record.update(status='running', started_at=utcnow().isoformat())
        _json(path, record)
        for op in preview['operations']:
            _native_download(config, op, staging)
            record['completed_downloads'] += 1
            _json(path, record)
        candidates = [_promote_candidate(config, record, op, staging) for op in preview['operations']]
        # Validate the entire candidate set before changing any live file.
        candidate_datadir = private_root / 'candidate_data'
        for live, candidate in candidates:
            relative = live.relative_to(Path(config['datadir']).resolve())
            destination = candidate_datadir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
        for row in quality_report(config, request['timerange'], request['timeframe'], request['detail_timeframe'],
                                  request['warmup_candles'], False, persist=False)['files']:
            live = _file(config, row['pair'], row['timeframe'], row['type'])
            destination = candidate_datadir / live.relative_to(Path(config['datadir']).resolve())
            if not destination.exists() and live.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(live, destination)
        candidate_cfg = {**config, 'datadir': candidate_datadir}
        candidate_report = quality_report(candidate_cfg, request['timerange'], request['timeframe'],
                                          request['detail_timeframe'], request['warmup_candles'], True, persist=False)
        record['candidate_status'] = candidate_report['status']
        record['candidate_issues'] = candidate_report['issues'][:ISSUE_LIMIT]
        _json(path, record)
        if candidate_report['status'] != 'ok':
            raise RuntimeError('Bản tải bù chưa đủ hoặc chưa đối chiếu được funding Binance; dữ liệu hiện tại giữ nguyên.')
        promoted_count = _commit_candidates(config, job_id, preview, candidates, private_root, candidate_report)
        record['status'] = 'success'
        record['promoted_files'] = promoted_count
        record['finished_at'] = utcnow().isoformat()
        record['audit_id'] = candidate_report['id']
    except Exception as exc:
        record.update(status='failed', error=f'{type(exc).__name__}: {exc}', finished_at=utcnow().isoformat())
    finally:
        _json(path, record)
        with _lock:
            if _active_job == job_id:
                _active_job = None
            ApiBG.download_data_running = False


@router.post('/data-repair')
def start_repair(body: RepairRequest, background_tasks: BackgroundTasks, config=Depends(get_config)):
    global _active_job
    with _lock:
        preview = _read_record(config, 'previews', body.preview_id)
        if preview['status'] != 'ready' or not preview['operations']:
            raise HTTPException(422, 'Không có dữ liệu cần tải bù trong bản xem trước.')
        if datetime.fromisoformat(preview['expires_at']) < utcnow():
            raise HTTPException(409, 'Bản xem trước đã hết hạn; kiểm tra lại dữ liệu.')
        if repair_active(config) or ApiBG.download_data_running or ApiBG.analysis_running:
            raise HTTPException(409, 'Chờ tác vụ nghiên cứu hoặc tải dữ liệu hiện tại hoàn tất.')
        _check_preview_sources(config, preview)
        id_ = uuid4().hex
        record = {'id': id_, 'preview_id': body.preview_id, 'status': 'pending', 'error': None,
                  'created_at': utcnow().isoformat(), 'completed_downloads': 0,
                  'total_downloads': len(preview['operations']), 'promoted_files': 0,
                  'candidate_status': None, 'candidate_issues': []}
        _json(_record_path(config, 'jobs', id_), record)
        _active_job = id_
        ApiBG.download_data_running = True
        background_tasks.add_task(_run_repair, id_, config)
        return record


@router.get('/data-repair/{job_id}')
def get_repair(job_id: str, config=Depends(get_config)):
    record = _read_record(config, 'jobs', job_id)
    if record['status'] in ('pending', 'running') and _active_job != job_id:
        record.update(status='interrupted', error='Dịch vụ đã khởi động lại; tải bù không tự chạy tiếp.',
                      finished_at=utcnow().isoformat())
        _json(_record_path(config, 'jobs', job_id), record)
    return record


@router.get('/data-repair')
def list_repairs(config=Depends(get_config)):
    repair_active(config)
    paths = sorted((_root(config) / 'jobs').glob('*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    return {'jobs': [json.loads(p.read_text(encoding='utf-8')) for p in paths[:20] if not p.is_symlink()]}
