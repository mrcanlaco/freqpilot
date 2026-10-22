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
from pydantic import BaseModel, Field
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
    return json.loads(p.read_text()) if p.exists() else {'name':name,'idea':'','notes':'','tags':[]}

class Research(BaseModel):
    idea: str=Field(default='',max_length=20000)
    notes: str=Field(default='',max_length=40000)
    tags: list[str]=Field(default_factory=list,max_length=12)

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
            out.append({'name':p.stem,'revision':doc['revision'],'modified':p.stat().st_mtime,
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
    result={'name':name,**req.model_dump(),'updated_at':datetime.now(timezone.utc).isoformat()}
    with lock:
        tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');os.replace(tmp,p)
    return result


class CheckStart(BaseModel):
    kind: Literal['lookahead','recursive']
    revision: str
    timeframe: str
    timerange: str
    minimum_trade_amount: int=Field(default=10,ge=1,le=500)
    targeted_trade_amount: int=Field(default=20,ge=1,le=200)

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
    settings={'strategy':name,'timeframe':req.timeframe,'timerange':req.timerange}
    if req.kind=='lookahead':
        settings.update(minimum_trade_amount=req.minimum_trade_amount,targeted_trade_amount=req.targeted_trade_amount)
        response=api_start_lookahead_analysis(LookaheadAnalysisRequest(**settings),background_tasks,config)
    else:
        settings['startup_candle']=[100,200,500,1000]
        response=api_start_recursive_analysis(RecursiveAnalysisRequest(**settings),background_tasks,config)
    job_id=str(response['job_id'])
    record={'id':job_id,'kind':req.kind,'strategy':name,'revision':doc['revision'],
            'settings':settings,'status':'pending','created_at':datetime.now(timezone.utc).isoformat(),
            'engine':'2026.9','preflight_id':preflight['id'],'result':None,'error':None}
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
        df=pd.read_feather(p)
        dates=pd.to_datetime(df['date'],utc=True)
        rows.append({'pair':pair,'timeframe':tf,'type':str(kind),'rows':len(df),
                     'start':dates.min().isoformat(),'end':dates.max().isoformat(),
                     'duplicates':int(dates.duplicated().sum()),'sorted':bool(dates.is_monotonic_increasing)})
    return {'files':rows,'fee':config.get('fee'),'wallet':config.get('dry_run_wallet'),
            'stake':config.get('stake_amount'),'max_open_trades':config.get('max_open_trades'),
            'pairs':config['exchange']['pair_whitelist'],'exchange':config['exchange']['name'],
            'mode':str(config.get('trading_mode')),'checked_at':datetime.now(timezone.utc).isoformat(),
            'note':'Phạm vi dữ liệu trên máy; không phải phép đối chiếu mới với Binance.'}

class Manifest(BaseModel):
    strategy:str
    revision:str
    settings:dict

@router.post('/manifests')
def manifest(req:Manifest,config=Depends(get_config)):
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
        if not dates.startts:raise ValueError('Chọn ngày bắt đầu.')
        if float(req.settings.get('dry_run_wallet',0))<=0 or float(req.settings.get('stake_amount',0))<=0:
            raise ValueError('Vốn và số tiền mỗi lệnh phải lớn hơn 0.')
        if not 1<=int(req.settings.get('max_open_trades',0))<=10:raise ValueError('Số lệnh tối đa phải từ 1 đến 10.')
        if config.get('fee') is None:raise ValueError('Cần khai báo phí rõ ràng trong cấu hình.')
    except (ValueError,ValidationError) as e:raise HTTPException(422,str(e))
    inventory=data(config)['files']
    for pair in config['exchange']['pair_whitelist']:
        for kind,tf in [('futures',req.settings.get('timeframe')),('futures',req.settings.get('timeframe_detail')),('mark',None),('funding_rate',None)]:
            matches=[x for x in inventory if x['pair']==pair and x['type']==kind and (tf is None or x['timeframe']==tf)]
            if not matches:raise HTTPException(422,f'Thiếu dữ liệu {kind} {tf or ""} cho {pair}.')
            row=matches[0]
            if row['duplicates'] or not row['sorted']:raise HTTPException(422,f'Dữ liệu {pair} có timestamp trùng hoặc chưa sắp xếp.')
            if dates.startts<datetime.fromisoformat(row['start']).timestamp():
                raise HTTPException(422,f'{kind} {pair} chỉ có từ {row["start"]}. Hãy chọn ngày sau đó hoặc tải thêm.')
    uid=uuid4().hex
    # Preserve source and imported local modules, excluding credentials and databases.
    sources={str(p.relative_to(root(config))):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in root(config).rglob('*.py') if not p.is_symlink() and '__pycache__' not in p.parts}
    result={'id':uid,'created_at':datetime.now(timezone.utc).isoformat(),'strategy':req.strategy,
            'revision':doc['revision'],'settings':req.settings,'engine':'2026.9','fee':config.get('fee'),
            'pairs':config['exchange']['pair_whitelist'],'source_hashes':sources,
            'status':'prepared','note':'Ghi nhận cấu hình trước khi gửi API backtest chính thức; không phải kết quả chạy.'}
    p=storage(config)/'manifests';p.mkdir(exist_ok=True)
    (p/(uid+'.json')).write_text(json.dumps(result,indent=2))
    (p/(uid+'.py')).write_text(doc['content'],encoding='utf-8')
    return result
