"""Named strategy-input presets using native parameter discovery and JSON export.

Never edits the live strategy/parameter file or a paper worker. Each run receives a copy.
"""
import hashlib
import json
import math
import re
import shutil
import threading
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import target, read, root
from freqtrade.rpc.api_server.api_studio import storage, write_check

router = APIRouter()
preset_lock = threading.RLock()
SPECIAL = {'roi', 'stoploss', 'trailing', 'max_open_trades'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def param_file(name, config):
    p = target(name, config).with_suffix('.json')
    if p.is_symlink() or (p.exists() and p.stat().st_size > 1_000_000):
        raise HTTPException(409, 'Tệp tham số liên kết hoặc quá lớn không được hỗ trợ.')
    return p


def schema_digest(fields):
    shape = [{k: v for k, v in row.items() if k != 'value'} for row in fields]
    return hashlib.sha256(json.dumps(shape, sort_keys=True, allow_nan=False).encode()).hexdigest()


def inspect_parameters(name, config, clear=True):
    from freqtrade.rpc.api_server.api_v1 import get_strategy
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    if ApiBG.analysis_running:
        raise HTTPException(409, 'Chờ tác vụ nghiên cứu hiện tại hoàn tất trước khi đọc tham số.')
    before = read(target(name, config))
    parameter = param_file(name, config)
    before_params = sha(parameter) if parameter.exists() else 'none'
    if clear:
        from freqtrade.rpc.api_server.api_runs import clear_local_imports
        clear_local_imports(config)
    native = get_strategy(name, config=deepcopy(config), rpc=None)
    fields = []
    supported = {'IntParameter', 'RealParameter', 'DecimalParameter', 'CategoricalParameter', 'BooleanParameter'}
    for p in native['params']:
        if p.param_type not in supported or p.space in SPECIAL:
            raise HTTPException(422, 'Có loại/nhóm tham số chưa hỗ trợ trên giao diện: ' + p.name)
        row = {'name': p.name, 'space': p.space, 'param_type': p.param_type,
               'value': p.value, 'load': p.load, 'optimize': p.optimize}
        for key in ('low', 'high', 'decimals', 'opt_range'):
            if hasattr(p, key):row[key] = getattr(p, key)
        # Match native JSON primitive types, without exposing arbitrary objects.
        from freqtrade.optimize.hyperopt_tools import hyperopt_serializer
        try:row = json.loads(json.dumps(row, default=hyperopt_serializer, allow_nan=False))
        except (ValueError,TypeError):raise HTTPException(422,'Khai báo tham số có giá trị không hữu hạn/không thể lưu JSON: '+p.name)
        if 'opt_range' in row and (len(row['opt_range']) > 200 or any(not scalar(v) for v in row['opt_range'])):
            raise HTTPException(422, 'Danh sách lựa chọn phải là giá trị đơn, tối đa 200 mục.')
        fields.append(row)
    fields.sort(key=lambda x: (x['space'], x['name']))
    if len(fields) > 200:
        raise HTTPException(422, 'Giao diện hiện hỗ trợ tối đa 200 tham số.')
    if read(target(name, config))['revision'] != before['revision'] or (sha(parameter) if parameter.exists() else 'none') != before_params:
        raise HTTPException(409, 'Mã hoặc tệp tham số vừa thay đổi. Tải lại trước khi lưu.')
    return {'strategy': name, 'revision': before['revision'], 'parameter_revision': before_params,
            'schema_revision': schema_digest(fields), 'fields': fields,
            'note': 'Giá trị được đọc bằng API strategy chính thức; chưa chạy backtest hay hyperopt.'}


def scalar(value):
    return value is None or type(value) in (str, bool, int) or (type(value) is float and math.isfinite(value))


def validate_values(values, fields):
    editable = {r['name']: r for r in fields if r['load']}
    if set(values) != set(editable):
        raise HTTPException(422, 'Bộ tham số phải chứa đúng các trường cho phép nạp; không thêm hoặc bỏ tên.')
    grouped = {}
    for name, value in values.items():
        row = editable[name]
        kind = row['param_type']
        if not scalar(value) or value is None:
            raise HTTPException(422, 'Giá trị tham số không hợp lệ: ' + name)
        if kind in ('CategoricalParameter', 'BooleanParameter'):
            if not any(type(value) is type(choice) and value == choice for choice in row['opt_range']):
                raise HTTPException(422, 'Lựa chọn ngoài danh sách: ' + name)
        else:
            if type(value) not in (int, float) or (kind == 'IntParameter' and type(value) is not int):
                raise HTTPException(422, 'Sai kiểu số của tham số: ' + name)
            if not row['low'] <= value <= row['high']:
                raise HTTPException(422, 'Giá trị ngoài giới hạn của tham số: ' + name)
            if kind == 'DecimalParameter' and Decimal(str(value)) != Decimal(str(value)).quantize(Decimal(1).scaleb(-row['decimals'])):
                raise HTTPException(422, 'Quá số chữ số thập phân cho phép: ' + name)
        grouped.setdefault(row['space'], {})[name] = value
    return grouped


def base_params(name, fields, config):
    from freqtrade.optimize.hyperopt_tools import HyperoptTools
    p = param_file(name, config)
    try:data = HyperoptTools.load_params_from_file(p) if p.exists() else {}
    except (ValueError,OSError):raise HTTPException(409,'Không đọc được JSON tham số gốc. Kiểm tra tệp trước khi lưu bộ mới.')
    if data and data.get('strategy_name') != name:
        raise HTTPException(409, 'Tệp tham số gốc không khớp tên chiến lược.')
    params = data.get('params', {})
    allowed = {r['space']: {v['name'] for v in fields if v['space'] == r['space']} for r in fields}
    allowed.update(roi=None, stoploss={'stoploss'}, max_open_trades={'max_open_trades'},
                   trailing={'trailing_stop', 'trailing_stop_positive', 'trailing_stop_positive_offset', 'trailing_only_offset_is_reached'})
    if not isinstance(params, dict):raise HTTPException(409, 'Tệp tham số gốc không đúng cấu trúc native.')
    for group, values in params.items():
        if group not in allowed or not isinstance(values, dict):
            raise HTTPException(409, 'Nhóm tham số gốc không được hỗ trợ: ' + group)
        for key, value in values.items():
            if (allowed[group] is not None and key not in allowed[group]) or (group == 'roi' and not re.fullmatch(r'\d+', key)) or not scalar(value):
                raise HTTPException(409, 'Tệp tham số gốc có trường chưa được hỗ trợ: ' + key)
    return params


def preset_root(name, config):
    read(target(name, config))
    p = storage(config) / 'presets' / name
    p.mkdir(parents=True, exist_ok=True)
    return p


def preset_path(name, uid, config):
    if not re.fullmatch(r'[0-9a-f]{32}', uid):raise HTTPException(422, 'Mã bộ tham số không hợp lệ.')
    p = preset_root(name, config) / uid
    if p.is_symlink() or not (p / 'record.json').is_file():raise HTTPException(404, 'Không có bộ tham số này.')
    return p


class SavePreset(BaseModel):
    label: str = Field(min_length=1, max_length=70)
    revision: str
    parameter_revision: str
    schema_revision: str
    values: dict = Field(max_length=200)


@router.get('/parameters/{name}')
def parameters(name: str, config=Depends(get_config)):
    with preset_lock:return inspect_parameters(name, config)


@router.post('/presets/{name}')
def save_preset(name: str, req: SavePreset, config=Depends(get_config)):
    with preset_lock:
        schema = inspect_parameters(name, config)
        if any(getattr(req, k) != schema[k] for k in ('revision', 'parameter_revision', 'schema_revision')):
            raise HTTPException(409, 'Mã hoặc định nghĩa tham số đã đổi. Đọc lại trước khi lưu bộ mới.')
        if not req.label.strip():raise HTTPException(422, 'Đặt tên cho bộ tham số.')
        grouped = validate_values(req.values, schema['fields'])
        if not grouped:raise HTTPException(422, 'Chiến lược chưa khai báo tham số cho phép nạp.')
        base = base_params(name, schema['fields'], config)
        parameter = param_file(name, config)
        if read(target(name,config))['revision'] != req.revision or (sha(parameter) if parameter.exists() else 'none') != req.parameter_revision:
            raise HTTPException(409,'Mã hoặc tệp tham số vừa thay đổi. Đọc lại trước khi lưu.')
        uid = uuid4().hex
        folder = preset_root(name, config) / uid
        folder.mkdir()
        from freqtrade.optimize.hyperopt_tools import HyperoptTools
        HyperoptTools.export_params({'params_not_optimized': base, 'params_details': grouped}, name, folder / 'params.json')
        record = {'id': uid, 'strategy': name, 'label': req.label.strip(),
                  'revision': schema['revision'], 'schema_revision': schema['schema_revision'],
                  'parameter_revision': schema['parameter_revision'], 'values': req.values,
                  'created_at': datetime.now(timezone.utc).isoformat(), 'native_sha256': sha(folder / 'params.json')}
        write_check(folder / 'record.json', record)
        return record


@router.get('/presets/{name}')
def list_presets(name: str, config=Depends(get_config)):
    records=[]
    for path in sorted(preset_root(name, config).glob('*/record.json'), key=lambda p:p.stat().st_mtime, reverse=True):
        if path.is_symlink() or path.parent.is_symlink():continue
        record = json.loads(path.read_text(encoding='utf-8'))
        record['valid'] = not (path.parent/'params.json').is_symlink() and (path.parent / 'params.json').is_file() and sha(path.parent / 'params.json') == record['native_sha256']
        records.append(record)
    return {'presets': records}


def load_preset(name, uid, config):
    folder = preset_path(name, uid, config)
    record = json.loads((folder / 'record.json').read_text(encoding='utf-8'))
    path = folder / 'params.json'
    if path.is_symlink() or not path.is_file() or sha(path) != record['native_sha256']:
        raise HTTPException(409, 'Tệp của bộ tham số đã thay đổi hoặc bị thiếu.')
    return record, path


def apply_preset(name, uid, inputs, config):
    """Validate against frozen source, then copy the native JSON into that run only."""
    from freqtrade.rpc.api_server.api_runs import clear_local_imports
    record, source = load_preset(name, uid, config)
    frozen_config = deepcopy(config)
    frozen_config.update(user_data_dir=inputs, strategy_path=str(inputs / 'strategies'), recursive_strategy_search=False)
    clear_local_imports(config)
    schema = inspect_parameters(name, frozen_config, clear=False)
    if record['strategy'] != name or record['revision'] != schema['revision'] or record['schema_revision'] != schema['schema_revision']:
        raise HTTPException(409, 'Bộ tham số thuộc phiên bản mã/định nghĩa khác. Chuẩn bị bộ mới cho mã hiện tại.')
    validate_values(record['values'], schema['fields'])
    destination = inputs / 'strategies' / (name + '.json')
    destination.write_bytes(source.read_bytes())
    if sha(destination) != record['native_sha256']:raise HTTPException(409, 'Bộ tham số đang thay đổi trong lúc sao chép.')
    return record


def snapshot_check_inputs(name, revision, uid, inputs, config):
    from freqtrade.rpc.api_server.api_runs import clear_local_imports
    source_root=root(config)
    destination=inputs/'strategies'
    destination.mkdir(parents=True)
    for path in source_root.rglob('*.py'):
        if '__pycache__' in path.parts:continue
        if path.is_symlink() or not path.resolve().is_relative_to(source_root):raise HTTPException(422,'Không dùng mã liên kết ngoài thư viện.')
        out=destination/path.relative_to(source_root)
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,out)
        if sha(out)!=sha(path):raise HTTPException(409,'Mã đang thay đổi khi chuẩn bị kiểm định.')
    if sha(destination/(name+'.py'))!=revision:raise HTTPException(409,'Mã đã đổi. Đọc lại trước khi kiểm định.')
    parameter=param_file(name,config)
    if parameter.exists():
        shutil.copyfile(parameter,destination/parameter.name)
        if sha(destination/parameter.name)!=sha(parameter):raise HTTPException(409,'Tham số đang thay đổi khi chuẩn bị kiểm định.')
    preset=apply_preset(name,uid,inputs,config) if uid else None
    clear_local_imports(config)
    hashes={p.relative_to(inputs).as_posix():sha(p) for p in destination.rglob('*') if p.is_file()}
    record={'source_hashes':hashes,'preset':preset,'source_snapshot':str(inputs)}
    write_check(inputs/'inputs.json',record)
    return record


@router.get('/presets/{name}/{uid}/download')
def download_preset(name: str, uid: str, config=Depends(get_config)):
    _, path = load_preset(name, uid, config)
    return FileResponse(path, media_type='application/json', filename=name+'-'+uid[:8]+'.json')
