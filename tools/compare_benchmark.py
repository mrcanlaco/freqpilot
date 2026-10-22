"""Read actual native result archives, never substitute missing engine results."""
import builtins
import json
import zipfile
from pathlib import Path

root=Path(__file__).resolve().parents[1]
names=['StarterFutures','FAdxSmaStrategy','FReinforcedStrategy','FSampleStrategy','FSupertrendStrategy','FOttStrategy','TrendFollowingStrategy','VolatilitySystem']
engines={}
for label,project in [('main',root.parent/'freqtrade'),('ultimate',root.parent/'freqtrade-ultimate-compare')]:
    found={}
    for path in sorted((project/'user_data/backtest_results').glob('*.zip'),reverse=True):
        with zipfile.ZipFile(path) as z:
            filename=next(n for n in z.namelist() if n.endswith('.json') and not n.endswith('_config.json'))
            data=json.loads(z.read(filename))
        for name,result in data['strategy'].items():
            if name in names and (name not in found or result.get('backtest_run_start_ts',0)>found[name]['result'].get('backtest_run_start_ts',0)):found[name]={'result':result,'file':path.name}
    if set(found)!=set(names):raise ValueError('Missing results in '+label)
    engines[label]=found
rows=[]
for name in names:
    a=engines['main'][name]['result'];b=engines['ultimate'][name]['result']
    fields=['pair','open_date','close_date','open_rate','close_rate','amount','funding_fees','profit_abs','exit_reason','leverage']
    equal=len(a['trades'])==len(b['trades']) and all(all(x.get(k)==y.get(k) for k in fields) for x,y in zip(a['trades'],b['trades']))
    rows.append({'strategy':name,'timeframe':a['timeframe'],'trades':a['total_trades'],
       'profit_usdt':a['profit_total_abs'],'profit_percent':a['profit_total']*100,
       'drawdown_percent':a['max_drawdown_account']*100,
       'winrate_percent':a['wins']/a['total_trades']*100 if a['total_trades'] else None,
       'profit_factor':a['profit_factor'] if a['losses'] else None,'native_profit_factor':a['profit_factor'],
       'sharpe':a['sharpe'],'longs':a.get('trade_count_long'),'shorts':a.get('trade_count_short'),
       'funding_usdt':sum(t.get('funding_fees',0) for t in a['trades']),
       'ultimate_profit_usdt':b['profit_total_abs'],'engine_trade_fields_match':equal,
       'all_leverage_1x':all(t.get('leverage',1)==1 for t in a['trades']+b['trades']),
       'main_result_file':engines['main'][name]['file'],'ultimate_result_file':engines['ultimate'][name]['file'],
       'start':a['backtest_start'],'end':a['backtest_end'],'small_sample':a['total_trades']<30})
out=root/'benchmarks';(out/'comparison.json').write_text(json.dumps(rows,indent=2))
for row in rows:print(row['strategy'],row['trades'],round(row['profit_usdt'],5),'matches Ultimate:',row['engine_trade_fields_match'])
assert all(row['all_leverage_1x'] for row in rows)

