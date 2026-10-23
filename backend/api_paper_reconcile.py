"""Read-only evidence and conservative comparisons for a FreqPilot dry-run profile.

Observation is sampled when requested.  Neither the trade database nor the paper
worker is modified.  Signals and real exchange fills are deliberately unobserved.
"""
import hashlib
import json
import math
import re
import shutil
import sqlite3
import tempfile
import threading
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_paper import checked_native, paper_root, verify_profile
from freqtrade.rpc.api_server.api_replay import checked_bundle
from freqtrade.rpc.api_server.api_runs import freeze, launch_snapshot, reproducible_config, digest
from freqtrade.rpc.api_server.api_studio import Manifest, write_check
from freqtrade.rpc.api_server.api_local_strategies import root as strategy_root

router = APIRouter()
_lock = threading.RLock()
_UID = re.compile(r'[0-9a-f]{32}\Z')
_MAX_TRADES = 5000
_TRADE_FIELDS = ('id', 'pair', 'is_short', 'is_open', 'open_date', 'close_date',
                 'open_rate', 'close_rate', 'stake_amount', 'amount', 'fee_open',
                 'fee_close', 'fee_open_cost', 'fee_close_cost', 'funding_fees',
                 'close_profit', 'close_profit_abs', 'exit_reason', 'enter_tag',
                 'leverage', 'strategy')
_ORDER_FIELDS = ('id', 'ft_trade_id', 'ft_order_side', 'ft_is_open', 'ft_amount',
                 'ft_price', 'status', 'side', 'average', 'filled', 'cost',
                 'order_date', 'order_filled_date', 'funding_fee', 'ft_order_tag')


def _now():
    return datetime.now(timezone.utc).isoformat()


def _date(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / (1000 if abs(value) > 1e11 else 1), timezone.utc)
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


def _safe(value):
    if isinstance(value, float) and not math.isfinite(value): return None
    return value


def _sessions_root(config):
    p = paper_root(config) / 'reconcile' / 'sessions'
    p.mkdir(parents=True, exist_ok=True)
    if p.is_symlink(): raise HTTPException(409, 'Kho phiên quan sát không hợp lệ.')
    return p


def _session_file(uid, config):
    if not _UID.fullmatch(uid): raise HTTPException(422, 'Mã phiên quan sát không hợp lệ.')
    p = _sessions_root(config) / (uid + '.json')
    if p.is_symlink() or not p.is_file(): raise HTTPException(404, 'Không có phiên quan sát này.')
    return p


def _load(uid, config):
    try: return json.loads(_session_file(uid, config).read_text(encoding='utf-8'))
    except (OSError, ValueError, TypeError) as error:
        raise HTTPException(409, 'Không đọc được bằng chứng phiên quan sát.') from error


def _native_view(profile, config):
    try:
        native = checked_native(config)  # only GET /show_config
        marker_fields = {key: native.get(key) for key in ('bot_name', 'strategy', 'timeframe',
                         'stake_amount', 'max_open_trades', 'dry_run_wallet', 'trading_mode', 'margin_mode')}
        return {'online': True, 'state': native.get('state'),
                'profile_matches': native.get('strategy') == profile['wrapper'],
                'configuration_marker': hashlib.sha256(json.dumps(marker_fields, sort_keys=True, default=str).encode()).hexdigest()}
    except HTTPException:
        return {'online': False, 'state': 'unavailable', 'profile_matches': False,
                'configuration_marker': None}


def _db_view(profile_cfg, folder, start, end):
    """A consistent SQLite backup from a read-only connection, including WAL rows."""
    if not profile_cfg['db_url'].startswith('sqlite:///'):
        raise HTTPException(409, 'Database paper không dùng SQLite riêng.')
    raw_db = Path(profile_cfg['db_url'].removeprefix('sqlite:///'))
    db = raw_db.resolve()
    if (raw_db.is_symlink() or not db.is_relative_to(folder.resolve())):
        raise HTTPException(409, 'Database paper nằm ngoài hồ sơ đã xác minh.')
    if not db.is_file():
        return {'available': False, 'trades': [], 'truncated': False,
                'reason': 'Database native chưa được tạo.'}
    try:
        with closing(sqlite3.connect(db.as_uri() + '?mode=ro', uri=True, timeout=5)) as source:
            with closing(sqlite3.connect(':memory:')) as snapshot:
                source.backup(snapshot)
                snapshot.row_factory = sqlite3.Row
                tables = {row[0] for row in snapshot.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {'trades', 'orders'} <= tables:
                    return {'available': False, 'trades': [], 'truncated': False,
                            'reason': 'Native database chưa có đủ bảng trades/orders.'}
                trade_cols = {row[1] for row in snapshot.execute('PRAGMA table_info(trades)')}
                order_cols = {row[1] for row in snapshot.execute('PRAGMA table_info(orders)')}
                if not set(_TRADE_FIELDS) <= trade_cols or not set(_ORDER_FIELDS) <= order_cols:
                    return {'available': False, 'trades': [], 'truncated': False,
                            'reason': 'Schema native khác bản đã kiểm tra.'}
                raw = snapshot.execute('SELECT ' + ','.join(_TRADE_FIELDS) + ' FROM trades ORDER BY id LIMIT ?',
                                       (_MAX_TRADES + 1,)).fetchall()
                truncated = len(raw) > _MAX_TRADES
                rows = []
                for item in raw[:_MAX_TRADES]:
                    trade = {key: _safe(item[key]) for key in _TRADE_FIELDS}
                    try:
                        opened = _date(trade['open_date'])
                        closed = _date(trade['close_date']) if trade['close_date'] else None
                    except (ValueError, TypeError, OverflowError):
                        trade['date_invalid'] = True
                        rows.append(trade)
                        continue
                    if opened >= end or (closed and closed < start): continue
                    trade['predates_session'] = opened < start
                    trade['continues_after_session'] = closed is None or closed > end
                    orders = snapshot.execute('SELECT ' + ','.join(_ORDER_FIELDS) +
                                              ' FROM orders WHERE ft_trade_id=? ORDER BY id', (trade['id'],)).fetchall()
                    trade['orders'] = [{key: _safe(order[key]) for key in _ORDER_FIELDS if key != 'ft_trade_id'}
                                       for order in orders]
                    rows.append(trade)
                return {'available': True, 'trades': rows, 'truncated': truncated,
                        'reason': 'Vượt giới hạn đọc an toàn.' if truncated else None}
    except (sqlite3.Error, OSError) as error:
        raise HTTPException(503, 'Không đọc được bản chụp database paper; có thể thử lại.') from error


def _sample(record, config):
    cfg, profile = verify_profile(record['profile_id'], config)
    if (profile['run_id'] != record['source_run_id'] or profile['revision'] != record['revision']
            or profile['config_sha256'] != record['profile_config_sha256']):
        raise HTTPException(409, 'Hồ sơ paper đã khác phiên quan sát.')
    stamp = _now()
    native = _native_view(profile, config)
    view = _db_view(cfg, paper_root(config) / 'profiles' / profile['id'],
                    _date(record['started_at']), _date(stamp))
    reason = None
    if not native['online']: reason = 'Không kết nối được worker paper tại lần đọc này.'
    elif not native['profile_matches']: reason = 'Worker đang dùng hồ sơ khác.'
    elif record['observations'] and native['configuration_marker'] != record['observations'][0]['native']['configuration_marker']:
        reason = 'Cấu hình native đã đổi trong phiên.'
    if not view['available']: reason = view['reason']
    if view['truncated']: reason = 'Database có hơn giới hạn 5000 giao dịch; đối chiếu chưa đầy đủ.'
    if any(t.get('strategy') != profile['wrapper'] for t in view['trades']):
        reason = 'Database chứa giao dịch của chiến lược khác hồ sơ đã xác minh.'
    if reason:
        record['gaps'].append({'observed_at': stamp, 'reason': reason})
    record['observations'].append({'at': stamp, 'native': native, 'database_available': view['available'],
                                   'trade_count': len(view['trades']), 'truncated': view['truncated']})
    record['paper_trades'] = view['trades']
    record['evidence'] = {'signals': 'unobserved', 'exchange_fills': 'unobserved',
                          'paper_fills': 'native dry-run database' if view['available'] else 'unavailable',
                          'observation_coverage': 'sampled; activity between reads is not continuously observed'}
    record['updated_at'] = stamp
    return record


class StartSession(BaseModel):
    profile_id: str
    label: str = Field(default='', max_length=70)


@router.post('/paper/reconcile/sessions')
def start_session(req: StartSession, config=Depends(get_config)):
    with _lock:
        _, profile = verify_profile(req.profile_id, config)
        native = _native_view(profile, config)
        if not native['online'] or not native['profile_matches']:
            raise HTTPException(409, 'Chỉ mở phiên quan sát cho hồ sơ đang chạy trên worker paper.')
        uid = uuid4().hex
        record = {'id': uid, 'profile_id': profile['id'], 'strategy': profile['strategy'],
                  'revision': profile['revision'], 'source_run_id': profile['run_id'],
                  'profile_config_sha256': profile['config_sha256'],
                  'source_hashes': profile['source_hashes'],
                  'settings': profile['settings'], 'engine': profile['engine'],
                  'label': req.label.strip() or profile['label'],
                  'status': 'observing', 'started_at': _now(), 'closed_at': None,
                  'observations': [], 'gaps': [], 'paper_trades': [], 'comparisons': [],
                  'warnings': ['Tín hiệu lịch sử và fill Binance thật không có trong database dry-run.']}
        _sample(record, config)
        write_check(_sessions_root(config) / (uid + '.json'), record)
        return record


@router.get('/paper/reconcile/sessions')
def list_sessions(profile_id: str | None = None, config=Depends(get_config)):
    if profile_id is not None and not _UID.fullmatch(profile_id):
        raise HTTPException(422, 'Mã hồ sơ không hợp lệ.')
    result = []
    for p in sorted(_sessions_root(config).glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True):
        if p.is_symlink(): continue
        try: item = json.loads(p.read_text(encoding='utf-8'))
        except (ValueError, OSError): continue
        if profile_id and item.get('profile_id') != profile_id: continue
        result.append({k: item.get(k) for k in ('id', 'profile_id', 'strategy', 'label', 'status', 'started_at', 'closed_at')}
                      | {'trade_count': len(item.get('paper_trades', [])),
                         'warning_count': len(item.get('warnings', [])) + len(item.get('gaps', []))})
        if len(result) >= 100: break
    return {'sessions': result}


@router.get('/paper/reconcile/sessions/{uid}')
def get_session(uid: str, config=Depends(get_config)):
    return _load(uid, config)


@router.post('/paper/reconcile/sessions/{uid}/capture')
def capture_session(uid: str, config=Depends(get_config)):
    with _lock:
        record = _load(uid, config)
        if record['status'] != 'observing': raise HTTPException(409, 'Phiên đã kết thúc.')
        _sample(record, config)
        write_check(_session_file(uid, config), record)
        return record


@router.post('/paper/reconcile/sessions/{uid}/close')
def close_session(uid: str, config=Depends(get_config)):
    with _lock:
        record = _load(uid, config)
        if record['status'] == 'closed': return record
        _sample(record, config)
        record['status'] = 'closed'
        record['closed_at'] = record['updated_at']
        write_check(_session_file(uid, config), record)
        return record


class CompareRequest(BaseModel):
    run_id: str


@router.post('/paper/reconcile/sessions/{uid}/backtest')
async def backtest_session(uid: str, background_tasks: BackgroundTasks, config=Depends(get_config)):
    """Launch one official native backtest if the live library still equals the paper source.

    A changed source/config is refused rather than silently using today's strategy.
    The ordinary frozen run and artifact are kept; comparison remains a separate action.
    """
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    with _lock:
        session = _load(uid, config)
        if session['status'] != 'closed': raise HTTPException(409, 'Kết thúc phiên trước khi chạy lại.')
        if ApiBG.analysis_running: raise HTTPException(409, 'Engine đang chạy tác vụ khác.')
        cfg, profile = verify_profile(session['profile_id'], config)
        if profile['config_sha256'] != session['profile_config_sha256']:
            raise HTTPException(409, 'Cấu hình hồ sơ paper đã đổi.')
        with checked_bundle(session['source_run_id'], config) as (_, origin, _):
            source_cfg = origin['config']
            detail = origin.get('settings', {}).get('timeframe_detail', '1m')
            protections = origin.get('settings', {}).get('enable_protections', False)
        names = {name.removeprefix('strategies/'): expected for name, expected in session['source_hashes'].items()
                 if name.startswith('strategies/') and not Path(name).name.startswith('FPPaper_')}
        library = strategy_root(config)
        current = {}
        for src in library.rglob('*.py'):
            if src.is_symlink() or not src.resolve().is_relative_to(library):
                raise HTTPException(409, 'Thư viện có mã liên kết không thể đối chiếu.')
            if '__pycache__' not in src.parts: current[src.relative_to(library).as_posix()] = digest(src)
        param = library / (session['strategy'] + '.json')
        if param.is_file():
            if param.is_symlink(): raise HTTPException(409, 'Tệp tham số là liên kết.')
            current[param.name] = digest(param)
        if current != names:
            raise HTTPException(409, 'Mã, helper hoặc tham số trong thư viện đã khác hồ sơ paper. Chưa chạy lại.')
        settings = {'timeframe': session['settings']['timeframe'], 'timeframe_detail': detail,
                    'timerange': f'{int(_date(session["started_at"]).timestamp())}-{math.ceil(_date(session["closed_at"]).timestamp())}',
                    'dry_run_wallet': session['settings']['wallet'],
                    'stake_amount': session['settings']['stake'],
                    'max_open_trades': session['settings']['max_open_trades'],
                    'enable_protections': protections}
        if reproducible_config(config, settings, session['strategy']) != reproducible_config(source_cfg, settings, session['strategy']):
            raise HTTPException(409, 'Cấu hình nghiên cứu hiện tại khác cấu hình đã tạo hồ sơ paper.')
        p, record = freeze(Manifest(strategy=session['strategy'], revision=session['revision'], settings=settings), config)
        frozen = json.loads((p / 'inputs.json').read_text(encoding='utf-8'))
        issues = _protocol_issues(session, frozen, record)
        if issues:
            record.update(status='failed', error='; '.join(issues))
            write_check(p / 'record.json', record)
            raise HTTPException(409, 'Đầu vào đã đóng băng khác hồ sơ: ' + '; '.join(issues))
        record['paper_reconcile'] = {'session_id': uid, 'profile_id': session['profile_id'],
                                     'observed_start': session['started_at'], 'observed_end': session['closed_at']}
        write_check(p / 'record.json', record)
        return await launch_snapshot(p, record, background_tasks, config, deepcopy(config))


def _native_result(uid, config):
    with checked_bundle(uid, config) as (bundle, frozen, record):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', str(record.get('filename', ''))):
            raise HTTPException(409, 'Tên kết quả native không hợp lệ.')
        member = 'output/' + record['filename'] + '.zip'
        with tempfile.TemporaryFile() as stream:
            with bundle.open(member) as source: shutil.copyfileobj(source, stream)
            stream.seek(0)
            with ZipFile(stream) as nested:
                stats = json.loads(nested.read(record['filename'] + '.json'))['strategy'][record['strategy']]
        if not isinstance(stats.get('trades'), list) or stats.get('total_trades') != len(stats['trades']):
            raise HTTPException(409, 'Kết quả native thiếu danh sách giao dịch.')
        return frozen, record, stats


def _protocol_issues(session, frozen, run):
    issues = []
    if session['strategy'] != run['strategy'] or session['revision'] != run['revision']:
        issues.append('Mã chiến lược hoặc revision khác hồ sơ paper.')
    if session['engine'] != run['engine']:
        issues.append('Engine khác hồ sơ paper.')
    archived = {name.removeprefix('strategies/'): digest for name, digest in session['source_hashes'].items()
                if name.startswith('strategies/') and not Path(name).name.startswith('FPPaper_')}
    candidate = {name.removeprefix('inputs/strategies/'): digest for name, digest in frozen['files'].items()
                 if name.startswith('inputs/strategies/') and name.endswith(('.py', '.json'))}
    if not archived or archived.get(session['strategy'] + '.py') != session['revision'] or archived != candidate:
        issues.append('Mã helper hoặc tham số trong backtest khác hồ sơ paper.')
    cfg = frozen['config']
    settings = session['settings']
    if (cfg.get('dry_run') is not True or cfg.get('trading_mode') != 'futures'
            or cfg.get('margin_mode') != 'isolated' or cfg.get('exchange', {}).get('name') != 'binance'):
        issues.append('Chế độ chạy backtest khác paper Binance Futures isolated.')
    checks = {'timeframe': cfg.get('timeframe'), 'wallet': cfg.get('dry_run_wallet'),
              'stake': cfg.get('stake_amount'), 'max_open_trades': cfg.get('max_open_trades'),
              'fee': cfg.get('fee')}
    for key, actual in checks.items():
        wanted = settings.get(key)
        if key in ('wallet', 'stake', 'max_open_trades', 'fee'):
            try: equal = float(actual) == float(wanted)
            except (TypeError, ValueError): equal = False
        else: equal = actual == wanted
        if not equal: issues.append('Cấu hình ' + key + ' khác phiên paper.')
    if cfg.get('exchange', {}).get('pair_whitelist') != settings.get('pairs'):
        issues.append('Danh sách cặp khác phiên paper.')
    from freqtrade.configuration import TimeRange
    try:
        timerange = TimeRange.parse_timerange(run['settings']['timerange'])
        start = _date(session['started_at']).timestamp()
        end = _date(session['closed_at']).timestamp()
        if not timerange.startts or timerange.startts > start or not timerange.stopts or timerange.stopts < end:
            issues.append('Backtest không bao phủ toàn bộ phiên quan sát.')
    except (KeyError, ValueError, TypeError):
        issues.append('Không xác minh được khoảng thời gian backtest.')
    return issues


def _number_diff(label, paper, backtest, kind=None):
    if paper is None or backtest is None:
        return {'field': label, 'status': 'insufficient', 'paper': paper, 'backtest': backtest}
    try:
        a, b = float(paper), float(backtest)
        if not math.isfinite(a) or not math.isfinite(b): raise ValueError
    except (TypeError, ValueError):
        return {'field': label, 'status': 'insufficient', 'paper': paper, 'backtest': backtest}
    delta = a - b
    result = {'field': label, 'status': 'matched' if delta == 0 else 'different',
              'paper': paper, 'backtest': backtest, 'delta': delta}
    if kind == 'price' and b: result['delta_bps'] = delta / b * 10000
    return result


def _time_diff(label, paper, backtest):
    if paper is None or backtest is None:
        return {'field': label, 'status': 'insufficient', 'paper': paper, 'backtest': backtest}
    try: delta = (_date(paper) - _date(backtest)).total_seconds()
    except (ValueError, TypeError, OverflowError):
        return {'field': label, 'status': 'insufficient', 'paper': paper, 'backtest': backtest}
    return {'field': label, 'status': 'matched' if delta == 0 else 'different',
            'paper': paper, 'backtest': backtest, 'delta_seconds': delta}


def _side_order(order, short):
    side = str(order.get('ft_order_side') or order.get('side') or '').lower()
    return 'entry' if side == ('sell' if short else 'buy') else 'exit'


def _compare_trade(paper, native, index):
    fields = []
    for key, other, kind in [('open_rate', 'open_rate', 'price'), ('close_rate', 'close_rate', 'price'),
                             ('stake_amount', 'stake_amount', None),
                             ('max_stake_amount', 'max_stake_amount', None),
                             ('amount', 'amount', None), ('leverage', 'leverage', None),
                             ('fee_open', 'fee_open', None), ('fee_close', 'fee_close', None),
                             ('funding_fees', 'funding_fees', None),
                             ('close_profit_abs', 'profit_abs', None),
                             ('close_profit', 'profit_ratio', None)]:
        fields.append(_number_diff(key, paper.get(key), native.get(other), kind))
    fields += [_time_diff('open_date', paper.get('open_date'), native.get('open_date')),
               _time_diff('close_date', paper.get('close_date'), native.get('close_date'))]
    for key in ('exit_reason', 'enter_tag'):
        a, b = paper.get(key), native.get(key)
        fields.append({'field': key, 'paper': a, 'backtest': b,
                       'status': 'insufficient' if a is None or b is None else 'matched' if a == b else 'different'})
    p_orders = []
    for order in paper.get('orders', []):
        try:
            if float(order.get('filled') or 0) > 0: p_orders.append(order)
        except (TypeError, ValueError): continue
    b_orders = native.get('orders')
    order_diffs = []
    if not isinstance(b_orders, list):
        fields.append({'field': 'orders', 'status': 'insufficient', 'reason': 'Native backtest không có orders.'})
    else:
        if not p_orders or not b_orders:
            fields.append({'field': 'orders', 'status': 'insufficient',
                           'reason': 'Thiếu lệnh con đã khớp ở một trong hai nguồn.'})
        if len(p_orders) != len(b_orders):
            fields.append({'field': 'order_count', 'paper': len(p_orders), 'backtest': len(b_orders), 'status': 'different'})
        for i, (a, b) in enumerate(zip(p_orders, b_orders)):
            p_side = _side_order(a, bool(paper['is_short']))
            b_side = 'entry' if b.get('ft_is_entry') else 'exit'
            order_diffs.append({'index': i, 'side': {'paper': p_side, 'backtest': b_side,
                                                      'status': 'matched' if p_side == b_side else 'different'},
                                'amount': _number_diff('order_amount', a.get('filled'), b.get('amount')),
                                'price': _number_diff('order_price', a.get('average') or a.get('ft_price'),
                                                      b.get('safe_price'), 'price'),
                                'cost': _number_diff('order_cost', a.get('cost'), b.get('cost')),
                                'filled_at': _time_diff('order_filled_date', a.get('order_filled_date'),
                                                        b.get('order_filled_timestamp'))})
    all_states = [f['status'] for f in fields]
    for order in order_diffs:
        all_states += [v['status'] for v in order.values() if isinstance(v, dict) and 'status' in v]
    status = 'different' if 'different' in all_states else 'insufficient' if 'insufficient' in all_states else 'matched'
    return {'paper_trade_id': paper['id'], 'backtest_index': index, 'status': status,
            'field_differences': [f for f in fields if f['status'] != 'matched'],
            'orders': order_diffs,
            'structure': {'paper_entry_orders': sum(_side_order(o, bool(paper['is_short'])) == 'entry' for o in p_orders),
                          'paper_exit_orders': sum(_side_order(o, bool(paper['is_short'])) == 'exit' for o in p_orders),
                          'backtest_entry_orders': sum(bool(o.get('ft_is_entry')) for o in b_orders or []),
                          'backtest_exit_orders': sum(not bool(o.get('ft_is_entry')) for o in b_orders or [])}}


def _compare_rows(session, native_trades, timeframe):
    from freqtrade.exchange import timeframe_to_seconds
    tolerance = timeframe_to_seconds(timeframe)
    start, end = _date(session['started_at']), _date(session['closed_at'])
    paper = session['paper_trades']
    predated = any(t.get('predates_session') for t in paper)
    bt = []
    for i, trade in enumerate(native_trades):
        try:
            if trade.get('open_date') and start <= _date(trade['open_date']) < end:
                bt.append((i, trade))
        except (ValueError, TypeError, OverflowError):
            return [{'paper_trade_id': None, 'backtest_index': i, 'status': 'insufficient',
                     'reasons': ['Ngày mở của giao dịch backtest không hợp lệ.']}]
    candidates = {}
    inverse = {}
    for p in paper:
        if p.get('predates_session') or p.get('date_invalid'): continue
        choices = [i for i, t in bt if t.get('pair') == p.get('pair')
                   and bool(t.get('is_short')) == bool(p.get('is_short'))
                   and abs((_date(t['open_date']) - _date(p['open_date'])).total_seconds()) <= tolerance]
        candidates[p['id']] = choices
        for i in choices: inverse.setdefault(i, []).append(p['id'])
    out, claimed = [], set()
    for p in paper:
        if p.get('predates_session'):
            out.append({'paper_trade_id': p['id'], 'status': 'insufficient',
                        'reasons': ['Vị thế đã tồn tại trước khi bắt đầu quan sát.']})
            continue
        if p.get('is_open') or p.get('continues_after_session') or p.get('date_invalid'):
            out.append({'paper_trade_id': p['id'], 'status': 'insufficient', 'reasons': ['Giao dịch chưa đóng trọn trong phiên hoặc ngày không hợp lệ.']})
            continue
        choices = candidates[p['id']]
        if len(choices) > 1 or (choices and len(inverse[choices[0]]) > 1):
            out.append({'paper_trade_id': p['id'], 'status': 'insufficient', 'reasons': ['Nhiều giao dịch có thể ghép; không chọn tùy tiện.']})
        elif not choices:
            out.append({'paper_trade_id': p['id'], 'status': 'different', 'reasons': ['Không có giao dịch backtest cùng cặp/chiều trong một khung nến.']})
        else:
            idx = choices[0]
            claimed.add(idx)
            out.append(_compare_trade(p, native_trades[idx], idx))
    for i, trade in bt:
        if i not in claimed and i not in inverse:
            out.append({'paper_trade_id': None, 'backtest_index': i,
                        'status': 'insufficient' if predated else 'different',
                        'reasons': ['Vị thế có trước phiên có thể ảnh hưởng giao dịch này.'] if predated else
                                   ['Backtest có giao dịch, paper không có giao dịch tương ứng trong phiên.'],
                        'pair': trade.get('pair'), 'open_date': trade.get('open_date')})
    return out


@router.post('/paper/reconcile/sessions/{uid}/compare')
def compare_session(uid: str, req: CompareRequest, config=Depends(get_config)):
    with _lock:
        session = _load(uid, config)
        if session['status'] != 'closed': raise HTTPException(409, 'Kết thúc phiên trước khi đối chiếu.')
        frozen, run, stats = _native_result(req.run_id, config)
        issues = _protocol_issues(session, frozen, run)
        try:
            actual_start, actual_end = _date(stats['backtest_start']), _date(stats['backtest_end'])
            if actual_start > _date(session['started_at']) or actual_end < _date(session['closed_at']):
                issues.append('Khoảng dữ liệu native thực dùng không bao phủ phiên quan sát.')
        except (KeyError, ValueError, TypeError, OverflowError):
            issues.append('Không xác minh được khoảng dữ liệu native thực dùng.')
        if session['gaps']: issues.append('Phiên có thời điểm thiếu quan sát hoặc cấu hình thay đổi.')
        if not session['observations'][-1]['database_available'] or session['observations'][-1]['truncated']:
            issues.append('Bản chụp database chưa đầy đủ.')
        if not session['paper_trades']: issues.append('Phiên paper chưa có giao dịch để đối chiếu.')
        if not stats['trades']: issues.append('Backtest chưa có giao dịch để đối chiếu.')
        if issues:
            result = {'session_id': uid, 'run_id': req.run_id, 'status': 'insufficient',
                      'counts': {'matched': 0, 'different': 0, 'insufficient': 0},
                      'trades': [], 'warnings': issues}
        else:
            trades = _compare_rows(session, stats['trades'], session['settings']['timeframe'])
            counts = {kind: sum(t['status'] == kind for t in trades) for kind in ('matched', 'different', 'insufficient')}
            status = 'different' if counts['different'] else 'insufficient' if counts['insufficient'] else 'matched'
            result = {'session_id': uid, 'run_id': req.run_id, 'status': status,
                      'counts': counts, 'trades': trades,
                      'warnings': ['Chỉ so dữ liệu paper dry-run native. Tín hiệu không được lưu đầy đủ; không quan sát fill Binance thật.']}
        result['created_at'] = _now()
        result['run_artifact_sha256'] = run['artifact_sha256']
        session['comparisons'].append(result)
        write_check(_session_file(uid, config), session)
        return result
