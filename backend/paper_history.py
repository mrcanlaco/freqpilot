"""Local lifecycle journal, separate from every Freqtrade trade database.

Requests and native observations are different facts. No inferred fills, session P&L,
or reconstruction of unobserved periods. Never store native credentials/responses.
"""
import hashlib
import inspect
import json
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from uuid import uuid4

from fastapi import HTTPException


def now(): return datetime.now(timezone.utc).isoformat()


def path(config):
    from freqtrade.rpc.api_server.api_paper import paper_root
    p = paper_root(config) / 'history.sqlite'
    if p.is_symlink(): raise HTTPException(409, 'Không dùng tệp lịch sử liên kết.')
    return p


@contextmanager
def connection(config, write=False):
    p = path(config)
    if not write and not p.exists():
        yield None
        return
    try:
        conn = sqlite3.connect(p if write else p.as_uri()+'?mode=ro', uri=not write, timeout=3)
        try:
            conn.row_factory = sqlite3.Row
            with conn:
                if write:
                    conn.execute('BEGIN IMMEDIATE')
                    conn.execute('CREATE TABLE IF NOT EXISTS events (id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TEXT NOT NULL, kind TEXT NOT NULL, profile_id TEXT, strategy TEXT, label TEXT, body TEXT NOT NULL)')
                    conn.execute('CREATE TABLE IF NOT EXISTS head (id INTEGER PRIMARY KEY CHECK (id=1), body TEXT NOT NULL)')
                    conn.execute('CREATE INDEX IF NOT EXISTS events_profile ON events(profile_id, id)')
                    conn.execute('CREATE INDEX IF NOT EXISTS events_strategy ON events(strategy, id)')
                yield conn
        finally: conn.close()
    except (sqlite3.Error, OSError, ValueError) as error:
        raise HTTPException(503, 'Không đọc/ghi được lịch sử paper. Kiểm tra trạng thái worker trước khi gửi lại thao tác.') from error


def append(conn, kind, owner, body):
    owner = owner or {}
    return conn.execute('INSERT INTO events(created_at,kind,profile_id,strategy,label,body) VALUES(?,?,?,?,?,?)',
                        (now(), kind, owner.get('id'), owner.get('strategy'), owner.get('label'),
                         json.dumps(body, ensure_ascii=False))).lastrowid


def owner_for_action(config, uid=None):
    from freqtrade.rpc.api_server.api_paper import paper_root, profile_path
    if uid:
        record = json.loads((profile_path(uid, config) / 'record.json').read_text(encoding='utf-8'))
        return {k: record.get(k) for k in ('id', 'strategy', 'label')}
    active = paper_root(config) / 'active/config.json'
    if active.is_file():
        wrapper = json.loads(active.read_text(encoding='utf-8'))['strategy']
        for file in (paper_root(config) / 'profiles').glob('*/record.json'):
            record = json.loads(file.read_text(encoding='utf-8'))
            if record.get('wrapper') == wrapper:
                return {k: record.get(k) for k in ('id', 'strategy', 'label')}
    return {}


def observe(config, status, native_config=None):
    active = next((p for p in status.get('profiles', []) if p['id'] == status.get('active_profile')), {})
    frame = {'online': bool(status.get('online')), 'state': status.get('state', 'unavailable'),
             'profile_id': active.get('id'), 'strategy': active.get('strategy'), 'label': active.get('label'),
             'native_strategy': status.get('native_strategy'),
             'configuration_marker': hashlib.sha256(native_config['bot_name'].encode()).hexdigest() if native_config and native_config.get('bot_name') else None}
    with connection(config, write=True) as conn:
        previous = conn.execute('SELECT body FROM head WHERE id=1').fetchone()
        previous = json.loads(previous['body']) if previous else None
        # Position count changes are trade activity, not lifecycle transitions.
        if previous == frame: return
        kind = 'baseline' if previous is None else 'observation' if frame['online'] else 'observation_gap'
        owner = active or ({'id': previous.get('profile_id'), 'strategy': previous.get('strategy'), 'label': previous.get('label')} if previous else {})
        append(conn, kind, owner, {'online': frame['online'], 'state': frame['state'],
                                  'previous_state': previous.get('state') if previous else None,
                                  'previous_profile_id': previous.get('profile_id') if previous else None,
                                  'open_trades': status.get('open_trades') if frame['online'] else None,
                                  'configuration_changed': bool(previous and previous['online'] and previous.get('configuration_marker') and frame['configuration_marker'] and previous['configuration_marker'] != frame['configuration_marker'] and frame['online']),
                                  'observation_restored': bool(previous and not previous['online'] and frame['online'])})
        conn.execute('INSERT INTO head(id,body) VALUES(1,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body', (json.dumps(frame),))


def audited(action):
    """Journal intent before the existing handler; never replace its native safety checks."""
    def decorate(fn):
        @wraps(fn)
        def wrapped(*args, **kwargs):
            bound = inspect.signature(fn).bind(*args, **kwargs)
            config = bound.arguments['config']
            owner = owner_for_action(config, bound.arguments.get('uid'))
            request_id = uuid4().hex
            journal_error, requested = None, False
            try:
                with connection(config, write=True) as conn:
                    append(conn, 'action_request', owner, {'request_id': request_id, 'action': action})
                requested = True
            except HTTPException as error:
                if action == 'start': raise
                # A broken journal must not prevent reducing paper risk or managing exits.
                journal_error = error.detail
            try:
                result = fn(*args, **kwargs)
            except Exception as error:
                if requested:
                    try:
                        with connection(config, write=True) as conn:
                            append(conn, 'action_result', owner, {'request_id': request_id, 'action': action,
                                   'outcome': 'error', 'http_status': getattr(error, 'status_code', 500)})
                    except HTTPException: pass
                raise
            expected = {'start': 'running', 'pause': 'paused', 'stop': 'stopped'}[action]
            confirmed = result.get('online') is True and result.get('state') == expected and result.get('active_profile') == owner.get('id')
            outcome = {'request_id': request_id, 'action': action,
                       'outcome': 'observed' if confirmed else 'unconfirmed',
                       'state': result.get('state'), 'active_profile': result.get('active_profile')}
            logged = False
            if requested:
                try:
                    with connection(config, write=True) as conn: append(conn, 'action_result', owner, outcome)
                    logged = True
                except HTTPException as error: journal_error = error.detail
            return {**result, 'action_result': {**outcome, 'logged': logged},
                    **({'history_error': journal_error} if journal_error else {})}
        return wrapped
    return decorate


def history(config, profile_id=None, strategy=None, before=None, limit=30):
    if profile_id and not re.fullmatch('[0-9a-f]{32}', profile_id): raise HTTPException(422, 'Mã hồ sơ không hợp lệ.')
    if strategy and not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}', strategy): raise HTTPException(422, 'Tên chiến lược không hợp lệ.')
    if not 1 <= limit <= 100 or (before is not None and before < 1): raise HTTPException(422, 'Trang lịch sử không hợp lệ.')
    where, values = [], []
    for key, value in [('profile_id', profile_id), ('strategy', strategy)]:
        if value:
            where.append(key+'=?'); values.append(value)
    if before is not None: where.append('id<?'); values.append(before)
    with connection(config) as conn:
        rows = conn.execute('SELECT * FROM events'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY id DESC LIMIT ?', [*values, limit+1]).fetchall() if conn else []
        first = conn.execute('SELECT created_at FROM events ORDER BY id LIMIT 1').fetchone() if conn else None
        events = [{**dict(row), 'body': json.loads(row['body'])} for row in rows[:limit]]
    return {'events': events, 'next_before': events[-1]['id'] if len(rows) > limit else None,
            'started_at': first['created_at'] if first else None,
            'note': 'Chỉ ghi từ khi có tính năng này. Yêu cầu và trạng thái native là hai loại bằng chứng riêng; không suy thời điểm thực thi, thời lượng chạy hoặc lợi nhuận phiên. Thay đổi ngoài workspace khi không có lần đọc có thể không xuất hiện.'}
