import json
import tempfile
import unittest
from zipfile import ZipFile
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException, BackgroundTasks
from freqtrade.rpc.api_server.api_local_strategies import Create, create, read
from freqtrade.rpc.api_server.api_studio import Manifest, CheckStart, start_check
from freqtrade.rpc.api_server.api_runs import freeze
from freqtrade.rpc.api_server.api_presets import (inspect_parameters, SavePreset, save_preset,
    list_presets, load_preset, apply_preset, download_preset, snapshot_check_inputs)


class PresetChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.base=Path(self.tmp.name)
        (self.base/'strategies').mkdir()
        (self.base/'data').mkdir()
        self.config={'user_data_dir':self.base,'datadir':self.base/'data','dry_run':True,
            'timeframe':'15m','dry_run_wallet':1000,'stake_amount':100,'stake_currency':'USDT',
            'max_open_trades':2,'trading_mode':'futures','margin_mode':'isolated','fee':.0005,
            'exchange':{'name':'binance','pair_whitelist':['BTC/USDT:USDT']}}
        doc=create(Create(name='PresetSample'),self.config)
        source=doc['content'].replace('from freqtrade.strategy import IStrategy',
            'from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter, BooleanParameter, CategoricalParameter')
        source=source.replace('    INTERFACE_VERSION = 3', '''    buy_length = IntParameter(2,40,default=10)
    sell_gate = DecimalParameter(.1,.9,default=.3,decimals=2)
    buy_kind = CategoricalParameter(['ema','sma'],default='ema')
    protection_enabled = BooleanParameter(default=True,space='protection')
    buy_locked = IntParameter(1,5,default=2,load=False)
    buy_params = {'buy_length':12}
    INTERFACE_VERSION = 3''')
        self.path=self.base/'strategies/PresetSample.py'
        self.path.write_text(source)
        self.revision=read(self.path)['revision']
        self.schema=inspect_parameters('PresetSample',self.config)
        self.values={p['name']:p['value'] for p in self.schema['fields'] if p['load']}

    def tearDown(self):self.tmp.cleanup()

    def request(self,values=None):
        return SavePreset(label='Bộ kiểm tra',**{k:self.schema[k] for k in ('revision','parameter_revision','schema_revision')},values=values or self.values)

    def test_native_discovery_preserves_parameter_types_spaces_and_class_values(self):
        fields={p['name']:p for p in self.schema['fields']}
        self.assertEqual(fields['buy_length']['value'],12)
        self.assertEqual(fields['buy_length']['low'],2)
        self.assertEqual(fields['sell_gate']['decimals'],2)
        self.assertEqual(fields['buy_kind']['opt_range'],['ema','sma'])
        self.assertIs(fields['protection_enabled']['value'],True)
        self.assertFalse(fields['buy_locked']['load'])

    def test_preset_exports_native_json_and_native_resolver_loads_it_without_live_edits(self):
        values={**self.values,'buy_length':18,'sell_gate':.45,'buy_kind':'sma','protection_enabled':False}
        original=self.path.read_bytes()
        saved=save_preset('PresetSample',self.request(values),self.config)
        inputs=self.base/'private'
        snapshot_check_inputs('PresetSample',self.revision,saved['id'],inputs,self.config)
        from freqtrade.resolvers.strategy_resolver import StrategyResolver
        strategy=StrategyResolver.load_strategy({**self.config,'user_data_dir':inputs,
            'strategy_path':str(inputs/'strategies'),'strategy':'PresetSample'})
        strategy.ft_load_hyper_params()
        self.assertEqual(strategy.buy_length.value,18)
        self.assertEqual(strategy.sell_gate.value,.45)
        self.assertEqual(strategy.buy_kind.value,'sma')
        self.assertIs(strategy.protection_enabled.value,False)
        self.assertEqual(strategy.buy_locked.value,2)
        self.assertEqual(original,self.path.read_bytes())
        self.assertFalse(self.path.with_suffix('.json').exists())
        data=json.loads(Path(download_preset('PresetSample',saved['id'],self.config).path).read_text())
        self.assertEqual(data['ft_stratparam_v'],1)
        self.assertEqual(data['strategy_name'],'PresetSample')

    def test_wrong_types_ranges_choices_unknown_names_and_disabled_fields_are_rejected(self):
        for changes in ({'buy_length':True},{'buy_length':2.5},{'buy_length':41},
                        {'sell_gate':float('nan')},{'sell_gate':.123},{'buy_kind':'other'},
                        {'protection_enabled':1},{'buy_locked':3},{'secret':'bad'}):
            with self.subTest(changes=changes),self.assertRaises(HTTPException):
                save_preset('PresetSample',self.request({**self.values,**changes}),self.config)
        missing=dict(self.values);missing.pop('buy_length')
        with self.assertRaises(HTTPException):save_preset('PresetSample',self.request(missing),self.config)

    def test_stale_source_schema_parameter_file_and_tampered_presets_are_rejected(self):
        for field in ('revision','schema_revision','parameter_revision'):
            with self.assertRaises(HTTPException):save_preset('PresetSample',self.request().model_copy(update={field:'old'}),self.config)
        saved=save_preset('PresetSample',self.request(),self.config)
        record,path=load_preset('PresetSample',saved['id'],self.config)
        path.write_text('{}')
        self.assertFalse(list_presets('PresetSample',self.config)['presets'][0]['valid'])
        with self.assertRaises(HTTPException):download_preset('PresetSample',saved['id'],self.config)
        with self.assertRaises(HTTPException):load_preset('PresetSample','../escape',self.config)

    def test_existing_native_roi_and_stoploss_are_retained_and_credentials_are_not_exportable(self):
        params={'strategy_name':'PresetSample','ft_stratparam_v':1,
            'params':{'buy':{'buy_length':14},'roi':{'0':.07},'stoploss':{'stoploss':-.03}}}
        self.path.with_suffix('.json').write_text(json.dumps(params))
        self.schema=inspect_parameters('PresetSample',self.config)
        self.values={p['name']:p['value'] for p in self.schema['fields'] if p['load']}
        self.assertEqual(self.values['buy_length'],14)
        saved=save_preset('PresetSample',self.request(),self.config)
        _,path=load_preset('PresetSample',saved['id'],self.config)
        exported=json.loads(path.read_text())['params']
        self.assertEqual(exported['roi'],{'0':.07})
        self.assertEqual(exported['stoploss'],{'stoploss':-.03})
        params['params']['api_server']={'password':'must-never-export'}
        self.path.with_suffix('.json').write_text(json.dumps(params))
        self.schema=inspect_parameters('PresetSample',self.config)
        with self.assertRaises(HTTPException):save_preset('PresetSample',self.request(),self.config)

    def test_frozen_run_gets_preset_file_and_records_exact_hash(self):
        saved=save_preset('PresetSample',self.request({**self.values,'buy_length':19}),self.config)
        req=Manifest(strategy='PresetSample',revision=self.revision,preset_id=saved['id'],settings={'timeframe':'15m'})
        with patch('freqtrade.rpc.api_server.api_runs.manifest',return_value={'id':'preflight'}):
            folder,record=freeze(req,self.config)
        frozen=json.loads((folder/'inputs.json').read_text())
        self.assertEqual(frozen['files']['inputs/strategies/PresetSample.json'],saved['native_sha256'])
        self.assertEqual(record['preset']['id'],saved['id'])
        self.assertFalse(self.path.with_suffix('.json').exists())

    def test_native_analysis_uses_private_source_and_preset_without_affecting_live_files(self):
        saved=save_preset('PresetSample',self.request({**self.values,'buy_length':17}),self.config)
        req=CheckStart(kind='lookahead',revision=self.revision,timeframe='15m',timerange='20260918-',preset_id=saved['id'])
        with patch('freqtrade.rpc.api_server.api_studio.manifest',return_value={'id':'preflight'}), \
             patch('freqtrade.rpc.api_server.api_analysis.api_start_lookahead_analysis',return_value={'job_id':'preset-check'}) as native:
            record=start_check('PresetSample',req,BackgroundTasks(),self.config)
        runtime=native.call_args[0][2]
        inputs=runtime['user_data_dir']
        self.assertNotEqual(inputs,self.base)
        self.assertEqual(json.loads((inputs/'strategies/PresetSample.json').read_text())['params']['buy']['buy_length'],17)
        self.assertEqual(record['preset']['id'],saved['id'])
        self.path.write_text('# later edit')
        self.assertIn('class PresetSample',(inputs/'strategies/PresetSample.py').read_text())

    def test_paper_profile_consumes_exact_preset_from_verified_backtest_package(self):
        from freqtrade.rpc.api_server.api_runs import finish, digest, run_path
        from freqtrade.rpc.api_server.api_studio import write_check
        from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
        from freqtrade.rpc.api_server.api_paper import PreparePaper, prepare_paper, verify_profile
        from freqtrade.resolvers.strategy_resolver import StrategyResolver
        self.config['api_server']={'username':'local','password':'local-test-only'}
        preset=save_preset('PresetSample',self.request({**self.values,'buy_length':23}),self.config)
        req=Manifest(strategy='PresetSample',revision=self.revision,preset_id=preset['id'],settings={})
        with patch('freqtrade.rpc.api_server.api_runs.manifest',return_value={'id':'preflight'}):
            folder,record=freeze(req,self.config)
        output=folder/'output/preset-native.zip'
        with ZipFile(output,'w') as native:
            native.write(folder/'inputs/strategies/PresetSample.py','preset-native_PresetSample.py')
            native.write(folder/'inputs/strategies/PresetSample.json','preset-native_PresetSample.json')
            native.writestr('preset-native.json',json.dumps({'strategy':{'PresetSample':{'total_trades':2,'profit_total_abs':0}}}))
        output.with_suffix('.meta.json').write_text(json.dumps({'PresetSample':{'run_id':'preset-native'}}))
        record['job_id']='preset-native'
        write_check(folder/'record.json',record)
        with patch.dict(ApiBG.jobs,{'preset-native':{'status':'success'}}):finish(record['id'],self.config)
        profile=prepare_paper(PreparePaper(run_id=record['id']),self.config)
        cfg,meta=verify_profile(profile['id'],self.config)
        cfg['user_data_dir']=Path(cfg['user_data_dir'])
        strategy=StrategyResolver.load_strategy(cfg)
        strategy.ft_load_hyper_params()
        self.assertEqual(strategy.buy_length.value,23)
        self.assertEqual(strategy.leverage(None,None,None,None,None,None,None),1)
        self.assertEqual(meta['preset']['native_sha256'],preset['native_sha256'])
        self.assertFalse(self.path.with_suffix('.json').exists())

    def test_native_zip_with_different_parameter_bytes_is_not_accepted(self):
        from freqtrade.rpc.api_server.api_runs import finish
        from freqtrade.rpc.api_server.api_studio import write_check
        from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
        preset=save_preset('PresetSample',self.request(),self.config)
        req=Manifest(strategy='PresetSample',revision=self.revision,preset_id=preset['id'],settings={})
        with patch('freqtrade.rpc.api_server.api_runs.manifest',return_value={'id':'preflight'}):folder,record=freeze(req,self.config)
        output=folder/'output/wrong-params.zip'
        with ZipFile(output,'w') as native:
            native.write(folder/'inputs/strategies/PresetSample.py','wrong-params_PresetSample.py')
            native.writestr('wrong-params_PresetSample.json','{}')
        record['job_id']='wrong-params'
        write_check(folder/'record.json',record)
        with patch.dict(ApiBG.jobs,{'wrong-params':{'status':'success'}}):finish(record['id'],self.config)
        result=json.loads((folder/'record.json').read_text())
        self.assertEqual(result['status'],'failed')
        self.assertIn('Tham số',result['error'])
        self.assertFalse((folder/'artifact.zip').exists())

    def test_check_source_changes_are_detected_before_recording_success(self):
        from freqtrade.rpc.api_server.api_studio import get_checks, check_dir, write_check
        from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
        inputs=check_dir('PresetSample',self.config)/'inputs'/'test'
        record=snapshot_check_inputs('PresetSample',self.revision,None,inputs,self.config)
        record.update(id='changed-check',status='pending',kind='recursive',strategy='PresetSample')
        write_check(check_dir('PresetSample',self.config)/'changed-check.json',record)
        (inputs/'strategies/PresetSample.py').write_text('# changed')
        with patch.dict(ApiBG.jobs,{'changed-check':{'status':'success','result':{},'error':None}}):
            result=get_checks('PresetSample',self.config)['checks'][0]
        self.assertEqual(result['status'],'failed')
        self.assertIn('bản sao',result['error'])


if __name__=='__main__':unittest.main()
