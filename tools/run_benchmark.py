"""Run an existing, frozen eight-strategy protocol. No optimization or paper changes."""
import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

root=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('--engine',choices=['main','ultimate'],required=True);parser.add_argument('--group',choices=['15m','5m','1h']);parser.add_argument('--grouped',action='store_true',help='Historical grouped protocol: shared maximum warmup can affect results');args=parser.parse_args()
container={'main':'codex-freqtrade-backtest-1','ultimate':'codex-ultimate-compare-backtest-1'}[args.engine]
groups={'15m':['StarterFutures'], '5m':['FReinforcedStrategy','TrendFollowingStrategy'], '1h':['FAdxSmaStrategy','FSampleStrategy','FSupertrendStrategy','FOttStrategy','VolatilitySystem']}
out=root/'benchmarks'/args.engine
if not args.grouped:out=out/'single'
out.mkdir(parents=True,exist_ok=True)
record={'engine':args.engine,'started_at':datetime.now(timezone.utc).isoformat(),'protocol':{'pairs':['BTC/USDT:USDT','ETH/USDT:USDT'],'timerange':'20260918-20261022','detail':'1m','fee_each_side':0.0005,'wallet':1000,'stake':100,'max_open_trades':2,'leverage':1,'optimization':False,'timeframe':'native per strategy'},'groups':[]}
if args.group and (out/'run.json').exists():record=json.loads((out/'run.json').read_text())
for tf,names in groups.items():
    if args.group and tf!=args.group:continue
    record['groups']=[g for g in record['groups'] if g['timeframe']!=tf]
    for batch in ([names] if args.grouped else [[name] for name in names]):
        command=['docker','exec',container,'freqtrade','backtesting','--config','user_data/config-benchmark.json','--strategy-list',*batch,'--timeframe',tf,'--timerange','20260918-20261022','--timeframe-detail','1m','--fee','0.0005','--dry-run-wallet','1000','--stake-amount','100','--max-open-trades','2','--cache','none','--export','trades']
        with (out/((tf if args.grouped else batch[0])+'.log')).open('w',encoding='utf-8') as f:run=subprocess.run(command,stdout=f,stderr=subprocess.STDOUT)
        item={'timeframe':tf,'strategies':batch,'returncode':run.returncode,'method':'grouped' if args.grouped else 'one strategy per process'}
        if run.returncode==0:
            last=subprocess.run(['docker','exec',container,'python','-c',"from pathlib import Path; print((Path('user_data/backtest_results')/'.last_result.json').read_text())"],capture_output=True,text=True,check=True)
            item['filename']=json.loads(last.stdout)['latest_backtest']
        record['groups'].append(item)
        (out/'run.json').write_text(json.dumps(record,indent=2))
        print(args.engine,','.join(batch),'OK' if run.returncode==0 else 'FAILED',flush=True)
record['completed_at']=datetime.now(timezone.utc).isoformat();(out/'run.json').write_text(json.dumps(record,indent=2))
if any(g['returncode'] for g in record['groups']):raise SystemExit(1)
