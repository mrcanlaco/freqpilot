import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import HTTPException, BackgroundTasks
from freqtrade.rpc.api_server.api_local_strategies import Create, Save, create, save
from freqtrade.rpc.api_server.api_studio import Research, Manifest, CheckStart, start_check, get_checks, library, save_research, get_research, versions, version, manifest

class StudioChecks(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.config={'user_data_dir':Path(self.tmp.name),'dry_run':True,'fee':0.0005,'exchange':{'pair_whitelist':['BTC/USDT:USDT','ETH/USDT:USDT']}}
        (Path(self.tmp.name)/'strategies').mkdir();self.doc=create(Create(name='ResearchSample'),self.config)
    def tearDown(self):self.tmp.cleanup()
    def test_research_survives_reload_without_executing_strategy(self):
        save_research('ResearchSample',Research(idea='Điều kiện short',notes='Chưa tối ưu'),self.config)
        self.assertEqual(get_research('ResearchSample',self.config)['idea'],'Điều kiện short')
        rows=library(self.config)['strategies'];self.assertEqual(rows[0]['timeframe'],'15m')
        self.assertEqual(rows[0]['research']['notes'],'Chưa tối ưu')
        self.assertFalse((Path(self.tmp.name)/'config.json').exists())
    def test_history_returns_exact_pre_save_source(self):
        save('ResearchSample',Save(content=self.doc['content']+'\n# edited',revision=self.doc['revision']),self.config)
        old=versions('ResearchSample',self.config)['versions'][0]['id']
        self.assertEqual(version('ResearchSample',old,self.config)['content'],self.doc['content'])
        with self.assertRaises(HTTPException):version('ResearchSample','../config.json',self.config)

    def test_library_favorite_action_preserves_research_and_normalized_tags(self):
        save_research('ResearchSample',Research(idea='Giữ ý tưởng',notes='Không mất ghi chú',tags=[' short ','Short','fibonacci']),self.config)
        result=save_research('ResearchSample',Research(is_favorite=True),self.config)
        self.assertEqual(result['idea'],'Giữ ý tưởng')
        self.assertEqual(result['notes'],'Không mất ghi chú')
        self.assertEqual(result['tags'],['short','fibonacci'])
        self.assertTrue(library(self.config)['strategies'][0]['research']['is_favorite'])
        # Older clients omit favorites: saving notes must retain the stored flag.
        save_research('ResearchSample',Research(notes='Ghi chú mới'),self.config)
        self.assertTrue(get_research('ResearchSample',self.config)['is_favorite'])
        save_research('ResearchSample',Research(tags=[],is_favorite=False),self.config)
        self.assertEqual(get_research('ResearchSample',self.config)['tags'],[])
        self.assertFalse(get_research('ResearchSample',self.config)['is_favorite'])

    def test_library_rejects_unbounded_or_control_character_tags(self):
        from pydantic import ValidationError
        for tags in (['a'*33],['one\ntwo'],['x']*13):
            with self.assertRaises(ValidationError):Research(tags=tags)
    def test_manifest_rejects_stale_revision_missing_funding_and_live_knobs(self):
        settings={'timerange':'20260918-','timeframe':'15m','timeframe_detail':'1m','dry_run_wallet':1000,'stake_amount':'100','max_open_trades':2,'enable_protections':False}
        with self.assertRaises(HTTPException):manifest(Manifest(strategy='ResearchSample',revision='old',settings=settings),self.config)
        with self.assertRaises(HTTPException):manifest(Manifest(strategy='ResearchSample',revision=self.doc['revision'],settings={**settings,'dry_run':False}),self.config)
        with patch('freqtrade.rpc.api_server.api_studio.data',return_value={'files':[]}):
            with self.assertRaises(HTTPException):manifest(Manifest(strategy='ResearchSample',revision=self.doc['revision'],settings=settings),self.config)
        rows=[]
        for pair in self.config['exchange']['pair_whitelist']:
            for kind,tf in [('futures','15m'),('futures','1m'),('funding_rate','1h'),('mark','1h')]:
                rows.append({'pair':pair,'type':kind,'timeframe':tf,'duplicates':0,'sorted':True,'start':'2026-09-15T00:00:00+00:00'})
        with patch('freqtrade.rpc.api_server.api_studio.data',return_value={'files':rows}):
            result=manifest(Manifest(strategy='ResearchSample',revision=self.doc['revision'],settings=settings),self.config)
        self.assertEqual(result['status'],'prepared')
        self.assertNotIn('password',str(result))
        self.assertEqual((Path(self.tmp.name)/'freqpilot/manifests'/(result['id']+'.py')).read_text(),self.doc['content'])

    def test_checks_delegate_to_official_api_and_preserve_terminal_result(self):
        from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
        req=CheckStart(kind='recursive',revision=self.doc['revision'],timeframe='15m',timerange='20260918-')
        with patch('freqtrade.rpc.api_server.api_studio.manifest',return_value={'id':'preflight-1'}),patch('freqtrade.rpc.api_server.api_analysis.api_start_recursive_analysis',return_value={'job_id':'test-native-job'}) as native:
            record=start_check('ResearchSample',req,BackgroundTasks(),self.config)
        self.assertEqual(native.call_args[0][0].strategy,'ResearchSample')
        self.assertEqual(record['revision'],self.doc['revision'])
        with patch.dict(ApiBG.jobs,{'test-native-job':{'status':'success','result':{'strategy':'ResearchSample','results':{}},'error':None,'progress_tasks':{}}}):
            records=get_checks('ResearchSample',self.config)['checks']
        self.assertEqual(records[0]['status'],'success')
        self.assertEqual(get_checks('ResearchSample',self.config)['checks'][0]['status'],'success')
        with self.assertRaises(HTTPException):start_check('ResearchSample',req.model_copy(update={'revision':'old'}),BackgroundTasks(),self.config)

    def test_missing_pending_native_job_is_interrupted_not_restarted(self):
        from freqtrade.rpc.api_server.api_studio import check_dir,write_check
        p=check_dir('ResearchSample',self.config)/'missing.json'
        write_check(p,{'id':'missing-job','status':'pending','strategy':'ResearchSample','kind':'recursive'})
        self.assertEqual(get_checks('ResearchSample',self.config)['checks'][0]['status'],'interrupted')

if __name__=='__main__':unittest.main()
