"""Small research annotations and strict, read-only comparison of frozen runs.

The native ZIP, inputs, run record and paper database are never edited. Notes
bind to the two immutable run hashes and carry their own optimistic revision.
"""
import hashlib
import json
import re
import threading
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_runs import digest, run_path
from freqtrade.rpc.api_server.api_studio import json_safe, storage, write_check

router = APIRouter()
_lock = threading.RLock()
HEX_ID = re.compile(r'[0-9a-f]{32}\Z')


def note_root(config):
    directory = storage(config) / 'run_notes'
    directory.mkdir(exist_ok=True)
    if directory.is_symlink():
        raise HTTPException(409, 'Kho ghi chú không hợp lệ.')
    return directory


def note_path(uid, config):
    if not HEX_ID.fullmatch(uid):
        raise HTTPException(422, 'Mã lần chạy không hợp lệ.')
    path = note_root(config) / (uid + '.json')
    if path.is_symlink():
        raise HTTPException(409, 'Tệp ghi chú liên kết không hợp lệ.')
    return path


def _safe_member(root, name, expected):
    member = Path(name)
    if member.is_absolute() or '..' in member.parts or not member.parts or member.parts[0] != 'inputs':
        raise HTTPException(409, 'Đường dẫn trong bản lưu không hợp lệ.')
    path = root / member
    if path.is_symlink() or not path.resolve().is_relative_to((root / 'inputs').resolve()):
        raise HTTPException(409, 'Đầu vào bản lưu liên kết ra ngoài.')
    if not path.is_file() or digest(path) != expected:
        raise HTTPException(409, 'Đầu vào bản lưu đã thay đổi: ' + name)


def _load_verified_run(uid, config):
    root = run_path(uid, config)
    files = (root / 'record.json', root / 'inputs.json', root / 'artifact.zip')
    if any(file.is_symlink() or not file.is_file() for file in files):
        raise HTTPException(409, 'Thiếu hoặc liên kết ngoài trong gói lần chạy.')
    try:
        record = json.loads(files[0].read_text(encoding='utf-8'))
        frozen = json.loads(files[1].read_text(encoding='utf-8'))
        if (record.get('id') != uid or frozen.get('id') != uid or record.get('status') != 'success'
                or record.get('strategy') != frozen.get('strategy')
                or record.get('revision') != frozen.get('revision')
                or record.get('settings') != frozen.get('settings')
                or record.get('engine') != frozen.get('engine')
                or digest(files[1]) != record.get('input_manifest_sha256')
                or digest(files[2]) != record.get('artifact_sha256')):
            raise ValueError('Gói lần chạy chưa thành công hoặc hash đầu vào/kết quả không khớp.')
        for name, expected in frozen['files'].items():
            _safe_member(root, name, expected)
        if not any(name.startswith('inputs/data/') for name in frozen['files']):
            raise ValueError('Bản lưu không chứa dữ liệu thị trường.')
        source = 'inputs/strategies/' + record['strategy'] + '.py'
        if frozen['files'].get(source) != record['revision']:
            raise ValueError('Mã chiến lược trong gói không khớp revision.')
        return record, frozen
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HTTPException(409, 'Không xác minh được lần chạy và đầu vào đã đóng băng.') from error


def _number(value):
    if value is None:
        return None
    if value == 'unlimited':
        return value
    try:
        number = Decimal(str(value))
        if not number.is_finite():
            raise ValueError()
        return str(number.normalize())
    except (InvalidOperation, ValueError):
        raise HTTPException(409, 'Giá trị số trong cấu hình đã lưu không hợp lệ.')


def _fingerprint(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def protocol_identity(record, frozen):
    cfg = frozen['config']
    settings = frozen['settings']
    exchange = cfg.get('exchange') or {}
    data_files = {name: expected for name, expected in frozen['files'].items()
                  if name.startswith('inputs/data/')}
    execution_keys = ('order_types', 'order_time_in_force', 'entry_pricing', 'exit_pricing',
                      'unfilledtimeout', 'pairlists', 'tradable_balance_ratio',
                      'use_exit_signal', 'exit_profit_only', 'exit_profit_offset',
                      'ignore_roi_if_entry_signal')
    execution = {key: cfg.get(key) for key in execution_keys}
    return json_safe({
        'strategy': record['strategy'], 'engine': record['engine'],
        'exchange': exchange.get('name'),
        'pairs': exchange.get('pair_whitelist'),  # order matters with a shared wallet
        'trading_mode': cfg.get('trading_mode'), 'margin_mode': cfg.get('margin_mode'),
        'timeframe': settings.get('timeframe', cfg.get('timeframe')),
        'timeframe_detail': settings.get('timeframe_detail', cfg.get('timeframe_detail')),
        'requested_timerange': settings.get('timerange'),
        'native_backtest_start': (record.get('summary') or {}).get('backtest_start'),
        'native_backtest_end': (record.get('summary') or {}).get('backtest_end'),
        'fee': _number(cfg.get('fee')),
        'wallet': _number(settings.get('dry_run_wallet', cfg.get('dry_run_wallet'))),
        'stake': _number(settings.get('stake_amount', cfg.get('stake_amount'))),
        'stake_currency': cfg.get('stake_currency'),
        'max_open_trades': _number(settings.get('max_open_trades', cfg.get('max_open_trades'))),
        'enable_protections': settings.get('enable_protections', cfg.get('enable_protections')),
        'liquidation_buffer': _number(cfg.get('liquidation_buffer')),
        'data_sha256': _fingerprint(data_files),
        'execution_config_sha256': _fingerprint(execution),
    })


def _default(uid, record, frozen):
    identity = protocol_identity(record, frozen)
    return {'run_id': uid, 'strategy': record['strategy'], 'label': '', 'tags': [],
            'notes': '', 'pinned_baseline': False,
            'artifact_sha256': record['artifact_sha256'],
            'input_manifest_sha256': record['input_manifest_sha256'],
            'protocol_hash': _fingerprint(identity)}


def _note_revision(note):
    return _fingerprint(note)


def _read_note(uid, config, record, frozen):
    path = note_path(uid, config)
    expected = _default(uid, record, frozen)
    if not path.is_file():
        return {**expected, 'note_revision': 'none'}
    try:
        stored = json.loads(path.read_text(encoding='utf-8'))
        if any(stored.get(k) != expected[k] for k in
               ('run_id', 'strategy', 'artifact_sha256', 'input_manifest_sha256', 'protocol_hash')):
            raise ValueError('Ghi chú gắn với phiên bản gói khác.')
        return {**stored, 'note_revision': _note_revision(stored)}
    except (OSError, ValueError, TypeError) as error:
        raise HTTPException(409, 'Ghi chú không còn khớp bản lưu; chưa ghi đè.') from error


class NoteUpdate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_note_revision: str
    label: str = Field(default='', max_length=70)
    tags: list[str] = Field(default_factory=list, max_length=8)
    notes: str = Field(default='', max_length=4000)
    pinned_baseline: bool = False

    @field_validator('expected_note_revision')
    @classmethod
    def valid_revision(cls, value):
        if value != 'none' and not re.fullmatch(r'[0-9a-f]{64}', value):
            raise ValueError('Revision ghi chú không hợp lệ.')
        return value

    @field_validator('label')
    @classmethod
    def clean_label(cls, value):
        if any(ord(char) < 32 for char in value):
            raise ValueError('Tên ghi chú không chứa ký tự điều khiển.')
        return value.strip()

    @field_validator('tags')
    @classmethod
    def clean_tags(cls, values):
        clean = []
        for value in values:
            item = value.strip()
            if not item or len(item) > 32 or any(ord(char) < 32 for char in item):
                raise ValueError('Nhãn phải dài 1–32 ký tự và không có ký tự điều khiển.')
            if item.casefold() not in {tag.casefold() for tag in clean}:
                clean.append(item)
        return clean


@router.get('/run-notes')
def list_notes(strategy: str | None = None, config=Depends(get_config)):
    """Metadata index only; GET one or compare performs full input verification."""
    with _lock:
        rows = []
        for file in sorted(note_root(config).glob('*.json'), key=lambda f: f.stat().st_mtime, reverse=True):
            if file.is_symlink() or not HEX_ID.fullmatch(file.stem):
                continue
            try:
                item = json.loads(file.read_text(encoding='utf-8'))
                if strategy and item.get('strategy') != strategy:
                    continue
                rows.append({**item, 'note_revision': _note_revision(item),
                             'verification': 'not_rechecked'})
            except (OSError, ValueError, TypeError):
                continue
            if len(rows) >= 100:
                break
        return {'notes': rows, 'note': 'Danh sách là chỉ mục ghi chú; mở một lần chạy để kiểm tra lại toàn bộ gói.'}


@router.get('/run-notes/{uid}')
def get_note(uid: str, config=Depends(get_config)):
    with _lock:
        record, frozen = _load_verified_run(uid, config)
        return {**_read_note(uid, config, record, frozen), 'verification': 'passed'}


@router.put('/run-notes/{uid}')
def put_note(uid: str, req: NoteUpdate, config=Depends(get_config)):
    with _lock:
        record, frozen = _load_verified_run(uid, config)
        current = _read_note(uid, config, record, frozen)
        if current['note_revision'] != req.expected_note_revision:
            raise HTTPException(409, 'Ghi chú đã thay đổi. Tải lại trước khi lưu.')
        changes = req.model_dump(exclude_unset=True)
        changes.pop('expected_note_revision', None)
        item = {**_default(uid, record, frozen),
                'label': current['label'], 'tags': current['tags'], 'notes': current['notes'],
                'pinned_baseline': current['pinned_baseline'], **changes}
        write_check(note_path(uid, config), item)
        return {**item, 'note_revision': _note_revision(item), 'verification': 'passed'}


class CompareRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    run_ids: list[str] = Field(min_length=2, max_length=8)


@router.post('/run-notes/compare')
def compare(req: CompareRequest, config=Depends(get_config)):
    if len(req.run_ids) != len(set(req.run_ids)):
        raise HTTPException(422, 'Chọn các lần chạy khác nhau.')
    with _lock:
        runs = []
        for uid in req.run_ids:
            record, frozen = _load_verified_run(uid, config)
            identity = protocol_identity(record, frozen)
            parameter_name = 'inputs/strategies/' + record['strategy'] + '.json'
            runs.append({'run_id': uid, 'protocol_hash': _fingerprint(identity),
                         'identity': identity, 'source_revision': record['revision'],
                         'parameter_sha256': frozen['files'].get(parameter_name),
                         'summary': record.get('summary'),
                         'note': _read_note(uid, config, record, frozen)})
        keys = runs[0]['identity']
        differences = {key: [run['identity'][key] for run in runs]
                       for key in keys if any(run['identity'][key] != runs[0]['identity'][key] for run in runs[1:])}
        required = ('strategy', 'engine', 'exchange', 'pairs', 'trading_mode', 'margin_mode',
                    'timeframe', 'requested_timerange', 'native_backtest_start',
                    'native_backtest_end', 'fee', 'wallet', 'stake', 'stake_currency',
                    'max_open_trades', 'data_sha256')
        missing = [key for key in required if any(run['identity'].get(key) in (None, [], '') for run in runs)]
        comparable = not differences and not missing
        return {'comparable': comparable, 'differences': differences, 'missing_fields': missing,
                'protocol_hash': runs[0]['protocol_hash'] if comparable else None,
                'runs': runs,
                'note': ('Cùng protocol cho phép so sánh kết quả; không chứng nhận lợi thế chiến lược.'
                         if comparable else 'Khác hoặc thiếu đầu vào; chỉ xem song song, không tính mức cải thiện trực tiếp.')}
