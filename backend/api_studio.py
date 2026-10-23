"""Research metadata and provenance around official Freqtrade. No trading routes."""
import ast
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from freqtrade.rpc.api_server.deps import get_config
from freqtrade.rpc.api_server.api_local_strategies import root, target, read, lock

router = APIRouter()

def storage(config):
    p=root(config).parent/'freqpilot'
    p.mkdir(exist_ok=True)
    return p

def meta_path(name,config):
    read(target(name,config))
    p=storage(config)/'research';p.mkdir(exist_ok=True)
    return p/(name+'.json')

def metadata(name,config):
    p=meta_path(name,config)
    defaults={'name':name,'idea':'','notes':'','tags':[],'is_favorite':False}
    return {**defaults,**json.loads(p.read_text())} if p.exists() else defaults

class Research(BaseModel):
    idea: str=Field(default='',max_length=20000)
    notes: str=Field(default='',max_length=40000)
    tags: list[str]=Field(default_factory=list,max_length=12)
    is_favorite: bool=False

    @field_validator('tags')
    @classmethod
    def clean_tags(cls,values):
        tags=[]
        for value in values:
            tag=value.strip()
            if not tag:continue
            if len(tag)>32 or any(ord(c)<32 for c in tag):
                raise ValueError('Mỗi nhãn tối đa 32 ký tự và không chứa ký tự điều khiển.')
            if tag.casefold() not in {t.casefold() for t in tags}:tags.append(tag)
        return tags

@router.get('/library')
def library(config=Depends(get_config)):
    out=[]
    for p in sorted(root(config).glob('*.py')):
        if p.is_symlink() or p.name.startswith('_'):continue
        try:
            doc=read(target(p.stem,config));tree=ast.parse(doc['content'])
            cls=next((n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==p.stem),None)
            if cls is None:continue
            attrs={}
            for n in cls.body:
                if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
                    key=n.targets[0].id
                    if key in {'timeframe','can_short','stoploss','startup_candle_count'}:
                        try:attrs[key]=ast.literal_eval(n.value)
                        except (ValueError,TypeError):pass
                elif isinstance(n,ast.AnnAssign) and isinstance(n.target,ast.Name):
                    key=n.target.id
                    if key in {'timeframe','can_short','stoploss','startup_candle_count'} and n.value is not None:
                        try:attrs[key]=ast.literal_eval(n.value)
                        except (ValueError,TypeError):pass
            out.append({'name':p.stem,'revision':doc['revision'],'modified':p.stat().st_mtime,
                        'parameter_revision': hashlib.sha256(p.with_suffix('.json').read_bytes()).hexdigest() if p.with_suffix('.json').is_file() and not p.with_suffix('.json').is_symlink() else 'none',
                        'protected':p.stem=='StarterFutures','research':metadata(p.stem,config),**attrs})
        except (HTTPException,SyntaxError,UnicodeError):
            out.append({'name':p.stem,'invalid':True})
    return {'strategies':out,'product':'FreqPilot','version':'0.1.0','engine':'2026.9','dry_run':True}

@router.get('/research/{name}')
def get_research(name:str,config=Depends(get_config)):
    return metadata(name,config)

@router.put('/research/{name}')
def save_research(name:str,req:Research,config=Depends(get_config)):
    p=meta_path(name,config)
    with lock:
        # Small library actions must not discard notes/tags saved in the editor.
        result={**metadata(name,config),**req.model_dump(exclude_unset=True),'name':name,
                'updated_at':datetime.now(timezone.utc).isoformat()}
        tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');os.replace(tmp,p)
    return result


class CheckStart(BaseModel):
    kind: Literal['lookahead','recursive']
    revision: str
    timeframe: str
    timerange: str
    minimum_trade_amount: int=Field(default=10,ge=1,le=500)
    targeted_trade_amount: int=Field(default=20,ge=1,le=200)
    preset_id: str | None=None

def check_dir(name,config):
    read(target(name,config))
    p=storage(config)/'checks'/name;p.mkdir(parents=True,exist_ok=True)
    return p

def json_safe(value):
    import math
    if isinstance(value,float) and not math.isfinite(value):return None
    if isinstance(value,dict):return {str(k):json_safe(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [json_safe(v) for v in value]
    return value

def write_check(path,record):
    with lock:
        tmp=path.with_suffix('.tmp')
        tmp.write_text(json.dumps(json_safe(record),ensure_ascii=False,default=str),encoding='utf-8')
        os.replace(tmp,path)

@router.post('/checks/{name}/start')
def start_check(name:str,req:CheckStart,background_tasks:BackgroundTasks,config=Depends(get_config)):
    from freqtrade.configuration import TimeRange
    from freqtrade.rpc.api_server.api_analysis import api_start_lookahead_analysis,api_start_recursive_analysis
    from freqtrade.rpc.api_server.api_schemas import LookaheadAnalysisRequest,RecursiveAnalysisRequest
    doc=read(target(name,config))
    if req.revision!=doc['revision']:raise HTTPException(409,'Mã đã đổi. Tải lại trước khi kiểm định.')
    try:TimeRange.parse_timerange(req.timerange)
    except ValueError as e:raise HTTPException(422,str(e))
    preflight=manifest(Manifest(strategy=name,revision=req.revision,settings={
        'timerange':req.timerange,'timeframe':req.timeframe,'timeframe_detail':'1m',
        'dry_run_wallet':config.get('dry_run_wallet',1000),'stake_amount':str(config.get('stake_amount',100)),
        'max_open_trades':config.get('max_open_trades',2),'enable_protections':False}),config)
    # Native analyses must use the selected code and parameter copy, not a file
    # subsequently edited in the library while a background job is running.
    from copy import deepcopy
    from freqtrade.rpc.api_server.api_presets import snapshot_check_inputs
    inputs=check_dir(name,config)/'inputs'/uuid4().hex
    input_record=snapshot_check_inputs(name,req.revision,req.preset_id,inputs,config)
    runtime=deepcopy(config)
    runtime.update(user_data_dir=inputs,strategy_path=str(inputs/'strategies'),recursive_strategy_search=False)
    settings={'strategy':name,'timeframe':req.timeframe,'timerange':req.timerange}
    if req.kind=='lookahead':
        settings.update(minimum_trade_amount=req.minimum_trade_amount,targeted_trade_amount=req.targeted_trade_amount)
        response=api_start_lookahead_analysis(LookaheadAnalysisRequest(**settings),background_tasks,runtime)
    else:
        settings['startup_candle']=[100,200,500,1000]
        response=api_start_recursive_analysis(RecursiveAnalysisRequest(**settings),background_tasks,runtime)
    job_id=str(response['job_id'])
    record={'id':job_id,'kind':req.kind,'strategy':name,'revision':doc['revision'],
            'settings':settings,'status':'pending','created_at':datetime.now(timezone.utc).isoformat(),
            'engine':'2026.9','preflight_id':preflight['id'],'result':None,'error':None,**input_record}
    p=check_dir(name,config)
    (p/(job_id+'.py')).write_text(doc['content'],encoding='utf-8')
    write_check(p/(job_id+'.json'),record)
    # FastAPI runs background tasks in order: save the native terminal result even
    # if the browser has closed before the analysis ends.
    background_tasks.add_task(get_checks,name,config)
    return record

@router.get('/checks/{name}')
def get_checks(name:str,config=Depends(get_config)):
    from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
    records=[]
    for p in sorted(check_dir(name,config).glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)[:20]:
        record=json.loads(p.read_text(encoding='utf-8'))
        if record['status'] in ('pending','running'):
            job=ApiBG.jobs.get(record['id'])
            if job is None:
                record.update(status='interrupted',error='Dịch vụ đã khởi động lại; job không còn trong engine. Không tự chạy lại.')
            else:
                record['status']=job['status']
                record['progress_tasks']=json_safe(job.get('progress_tasks',{}))
                record['result']=json_safe(job.get('result')) if job['status'] in ('success','failed') else None
                record['error']=job.get('error')
            if record['status']=='success' and record.get('source_hashes'):
                source=Path(record['source_snapshot'])
                if not source.resolve().is_relative_to(check_dir(name,config).resolve()) or any(
                    not (source/key).is_file() or hashlib.sha256((source/key).read_bytes()).hexdigest()!=expected
                    for key,expected in record['source_hashes'].items()):
                    record.update(status='failed',error='Mã/tham số trong bản sao kiểm định đã đổi hoặc bị thiếu. Không xác nhận kết quả cho bản nguồn này.')
            write_check(p,record)
        records.append(record)
    return {'checks':records,'note':'Kết quả là chẩn đoán trên mẫu dữ liệu đã chọn, không chứng nhận lợi nhuận hoặc không có bias ở mọi trường hợp.'}

@router.get('/versions/{name}')
def versions(name:str,config=Depends(get_config)):
    read(target(name,config))
    p=root(config).parent/'strategy_editor_backups'/name
    return {'versions':[{'id':f.name,'saved_at':f.stat().st_mtime} for f in sorted(p.glob('*.py'),reverse=True) if not f.is_symlink()]}

@router.get('/versions/{name}/{version}')
def version(name:str,version:str,config=Depends(get_config)):
    import re
    read(target(name,config))
    if not re.fullmatch(r'\d{8}T\d{12}Z\.py',version):raise HTTPException(422,'Phiên bản không hợp lệ.')
    p=root(config).parent/'strategy_editor_backups'/name/version
    if p.is_symlink() or not p.is_file():raise HTTPException(404,'Không có phiên bản này.')
    return {'content':p.read_text(encoding='utf-8'),'version':version}

@router.get('/data')
def data(config=Depends(get_config)):
    import pandas as pd
    from freqtrade.data.history import get_datahandler
    from freqtrade.enums import TradingMode, CandleType
    root(config)
    dh=get_datahandler(config['datadir'],config.get('dataformat_ohlcv'))
    available=dh.ohlcv_get_available_data(config['datadir'],TradingMode.FUTURES)
    rows=[]
    for pair,tf,kind in available:
        if pair not in config['exchange']['pair_whitelist']:continue
        p=dh._pair_data_filename(Path(config['datadir']),pair,tf,candle_type=kind)
        if not p.is_file():continue
        try:
            df=pd.read_feather(p)
            dates=pd.to_datetime(df['date'],utc=True)
            first=dates.min().isoformat() if len(dates) else None
            last=dates.max().isoformat() if len(dates) else None
            rows.append({'pair':pair,'timeframe':tf,'type':str(kind),'rows':len(df),
                         'start':first,'end':last,'duplicates':int(dates.duplicated().sum()),
                         'sorted':bool(dates.is_monotonic_increasing)})
        except (OSError,ValueError,KeyError,TypeError) as error:
            rows.append({'pair':pair,'timeframe':tf,'type':str(kind),'rows':0,
                         'start':None,'end':None,'duplicates':0,'sorted':False,
                         'error':'Không đọc được dữ liệu thô: '+type(error).__name__})
    return {'files':rows,'fee':config.get('fee'),'wallet':config.get('dry_run_wallet'),
            'stake':config.get('stake_amount'),'max_open_trades':config.get('max_open_trades'),
            'pairs':config['exchange']['pair_whitelist'],'exchange':config['exchange']['name'],
            'mode':str(config.get('trading_mode')),'checked_at':datetime.now(timezone.utc).isoformat(),
            'note':'Phạm vi dữ liệu trên máy; không phải phép đối chiếu mới với Binance.'}

class Manifest(BaseModel):
    strategy:str
    revision:str
    settings:dict
    preset_id:str | None=None

@router.post('/manifests')
def manifest(req:Manifest,config=Depends(get_config)):
    from freqtrade.rpc.api_server.api_data_quality import data_source_lock
    with data_source_lock:
        return _manifest_locked(req,config)


def _manifest_locked(req:Manifest,config):
    doc=read(target(req.strategy,config))
    if doc['revision']!=req.revision:raise HTTPException(409,'Mã đã đổi. Tải lại trước khi chạy.')
    allowed={'timerange','timeframe','timeframe_detail','dry_run_wallet','max_open_trades','stake_amount','enable_protections'}
    if any(k not in allowed for k in req.settings):raise HTTPException(422,'Tham số không được hỗ trợ.')
    from freqtrade.configuration import TimeRange
    from freqtrade.rpc.api_server.api_schemas import BacktestRequest
    from pydantic import ValidationError
    try:
        BacktestRequest.model_validate({'strategy':req.strategy,**req.settings})
        dates=TimeRange.parse_timerange(req.settings.get('timerange',''))
        if not dates.startts or not dates.stopts:raise ValueError('Chọn ngày bắt đầu và kết thúc rõ ràng để kiểm tra toàn bộ dữ liệu.')
        if float(req.settings.get('dry_run_wallet',0))<=0 or float(req.settings.get('stake_amount',0))<=0:
            raise ValueError('Vốn và số tiền mỗi lệnh phải lớn hơn 0.')
        if not 1<=int(req.settings.get('max_open_trades',0))<=10:raise ValueError('Số lệnh tối đa phải từ 1 đến 10.')
        if config.get('fee') is None:raise ValueError('Cần khai báo phí rõ ràng trong cấu hình.')
    except (ValueError,ValidationError) as e:raise HTTPException(422,str(e))
    from freqtrade.rpc.api_server.api_data_quality import quality_report, guard_research
    guard_research(config)
    tree=ast.parse(doc['content'])
    strategy_cls=next((node for node in tree.body if isinstance(node,ast.ClassDef) and node.name==req.strategy),None)
    warmup=None
    if strategy_cls:
        for node in strategy_cls.body:
            if isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id=='startup_candle_count':
                try:warmup=int(ast.literal_eval(node.value))
                except (ValueError,TypeError):pass
            elif isinstance(node,ast.AnnAssign) and isinstance(node.target,ast.Name) and node.target.id=='startup_candle_count' and node.value is not None:
                try:warmup=int(ast.literal_eval(node.value))
                except (ValueError,TypeError):pass
    if warmup is None or warmup<0 or warmup>10000:
        raise HTTPException(422,'Không xác định được startup_candle_count từ mã. Khai báo một số nguyên cố định trong chiến lược trước khi chạy.')
    audit=quality_report(config,req.settings['timerange'],req.settings.get('timeframe','15m'),
                         req.settings.get('timeframe_detail','1m'),warmup,False)
    if audit['status'] in ('missing','invalid'):
        reasons='; '.join(x['message'] for x in audit['issues'][:3] if x['severity'] in ('missing','invalid'))
        raise HTTPException(422,'Dữ liệu thô chưa đủ hoặc sai: '+(reasons or audit['status']))
    uid=uuid4().hex
    # Preserve source and imported local modules, excluding credentials and databases.
    sources={str(p.relative_to(root(config))):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root(config).rglob('*.py') if not p.is_symlink() and '__pycache__' not in p.parts}
    result={'id':uid,'created_at':datetime.now(timezone.utc).isoformat(),'strategy':req.strategy,
            'revision':doc['revision'],'settings':req.settings,'engine':'2026.9','fee':config.get('fee'),
            'pairs':config['exchange']['pair_whitelist'],'source_hashes':sources,
            'data_audit':{'id':audit['id'],'status':audit['status'],'version':audit['version'],
                          'checked_at':audit['checked_at'],'files':[{'pair':f['pair'],'timeframe':f['timeframe'],
                          'type':f['type'],'sha256':f['sha256']} for f in audit['files']]},
            'status':'prepared','note':'Ghi nhận cấu hình trước khi gửi API backtest chính thức; không phải kết quả chạy.'}
    p=storage(config)/'manifests';p.mkdir(exist_ok=True)
    (p/(uid+'.json')).write_text(json.dumps(result,indent=2))
    (p/(uid+'.py')).write_text(doc['content'],encoding='utf-8')
    return result
