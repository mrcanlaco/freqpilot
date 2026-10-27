import json
import hashlib
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
from uuid import uuid4
from zipfile import ZipFile

from fastapi import HTTPException
from freqtrade.rpc.api_server.api_local_strategies import Create, create
from freqtrade.rpc.api_server.api_runs import digest
from freqtrade.rpc.api_server.api_studio import write_check
from freqtrade.rpc.api_server.api_paper import (bootstrap, PreparePaper, prepare_paper, paper_root,
    profile_path, verify_profile, start_paper, stop_paper, checked_native, load_paper_base,
    profile_visibility, archive_profile, restore_profile, _paper_status)


class PaperChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / 'strategies').mkdir()
        self.config = {'user_data_dir': self.base, 'dry_run': True, 'fee': .0005,
                       'trading_mode': 'futures', 'margin_mode': 'isolated',
                       'timeframe': '15m', 'dry_run_wallet': 1000, 'stake_amount': 100,
                       'max_open_trades': 2, 'stake_currency': 'USDT',
                       'exchange': {'name': 'binance', 'key': '', 'secret': '',
                                    'pair_whitelist': ['BTC/USDT:USDT','ETH/USDT:USDT']},
                       'api_server': {'username': 'local', 'password': 'not-an-exchange-key'}}
        self.doc = create(Create(name='PaperSample'), self.config)
        self.uid = uuid4().hex
        self.origin = self.base / 'freqpilot/runs' / self.uid
        self.origin.mkdir(parents=True)
        from freqtrade.rpc.api_server.api_runs import reproducible_config
        public = reproducible_config(self.config, {}, 'PaperSample')
        frozen = {'strategy': 'PaperSample', 'revision': self.doc['revision'],
                  'config': public, 'files': {'inputs/strategies/PaperSample.py': self.doc['revision']}}
        params = json.dumps({'strategy_name':'PaperSample','ft_stratparam_v':1,
                             'params':{'roi':{'0':.07},'stoploss':{'stoploss':-.03}}})
        frozen['files']['inputs/strategies/PaperSample.json'] = hashlib.sha256(params.encode()).hexdigest()
        manifest = self.origin / 'inputs.json'
        manifest.write_text(json.dumps(frozen))
        with ZipFile(self.origin / 'artifact.zip', 'w') as bundle:
            bundle.write(manifest, 'inputs.json')
            bundle.writestr('inputs/strategies/PaperSample.py', self.doc['content'])
            bundle.writestr('inputs/strategies/PaperSample.json', params)
        write_check(self.origin / 'record.json', {'id': self.uid, 'strategy': 'PaperSample',
            'revision': self.doc['revision'], 'status': 'success',
            'input_manifest_sha256': digest(manifest), 'artifact_sha256': digest(self.origin / 'artifact.zip'),
            'summary': {'total_trades': 3, 'profit_total_abs': -2}})
        bootstrap(self.config)

    def tearDown(self):
        self.tmp.cleanup()

    def prepared(self):
        return prepare_paper(PreparePaper(run_id=self.uid), self.config)

    def test_optimization_lineage_comes_from_verified_archive_and_train_is_explicit(self):
        manifest = self.origin / 'inputs.json'
        frozen = json.loads(manifest.read_text())
        frozen['optimization'] = {'id': 'a' * 32, 'epoch': 3, 'mode': 'train'}
        manifest.write_text(json.dumps(frozen))
        with ZipFile(self.origin / 'artifact.zip') as bundle:
            members = {name: bundle.read(name) for name in bundle.namelist() if name != 'inputs.json'}
        with ZipFile(self.origin / 'artifact.zip', 'w') as bundle:
            bundle.write(manifest, 'inputs.json')
            for name, content in members.items():
                bundle.writestr(name, content)
        record_path = self.origin / 'record.json'
        source = json.loads(record_path.read_text())
        source.update(input_manifest_sha256=digest(manifest), artifact_sha256=digest(self.origin / 'artifact.zip'),
                      optimization={'id': 'b' * 32, 'epoch': 9, 'mode': 'oos'})
        write_check(record_path, source)
        profile = self.prepared()
        self.assertEqual(profile['optimization'], frozen['optimization'])
        self.assertTrue(any('chưa phải kiểm định ngoài mẫu' in warning for warning in profile['warnings']))
        self.assertTrue(verify_profile(profile['id'], self.config)[1]['dry_run'])

    def test_bootstrap_is_stopped_and_never_copies_exchange_keys(self):
        cfg = json.loads(bootstrap(self.config).read_text())
        self.assertTrue(cfg['dry_run'])
        self.assertEqual(cfg['initial_state'], 'stopped')
        self.assertEqual(cfg['strategy'], 'FPPaperIdle')
        self.assertEqual(cfg['exchange']['key'], '')
        self.assertEqual(cfg['margin_mode'], 'isolated')
        with self.assertRaises(HTTPException):
            bootstrap({**self.config, 'dry_run': False})
        with self.assertRaises(HTTPException):
            paper_root({**self.config, 'exchange': {**self.config['exchange'], 'key': 'forbidden'}})

    def test_profile_uses_archived_source_and_own_db_with_fixed_1x_wrapper(self):
        (self.base / 'strategies/PaperSample.py').write_text('# changed live source')
        profile = self.prepared()
        path = profile_path(profile['id'], self.config)
        cfg, record = verify_profile(profile['id'], self.config)
        self.assertEqual((path / 'strategies/PaperSample.py').read_text(), self.doc['content'])
        self.assertIn(str(path), cfg['db_url'])
        self.assertTrue(profile['warnings'])
        namespace = {'__file__': str(path / 'strategies' / (record['wrapper'] + '.py'))}
        exec((path / 'strategies' / (record['wrapper'] + '.py')).read_text(), namespace)
        self.assertEqual(namespace[record['wrapper']].leverage(None, proposed_leverage=10), 1.0)
        self.assertEqual(json.loads(bootstrap(self.config).read_text())['strategy'], 'FPPaperIdle')

    def test_tampered_profile_is_not_activated(self):
        profile = self.prepared()
        path = profile_path(profile['id'], self.config)
        (path / 'strategies/PaperSample.py').write_text('# tampered')
        with patch('freqtrade.rpc.api_server.api_paper.native') as api:
            with self.assertRaises(HTTPException): start_paper(profile['id'], self.config)
        api.assert_not_called()

    def test_inactive_profile_can_be_hidden_and_restored_without_changing_frozen_inputs(self):
        profile = self.prepared()
        folder = profile_path(profile['id'], self.config)
        before = digest(folder / 'record.json'), digest(folder / 'config.json')
        with patch('freqtrade.rpc.api_server.api_paper.checked_native',
                   return_value={'strategy': 'FPPaperIdle', 'state': 'stopped', 'dry_run': True}), \
             patch('freqtrade.rpc.api_server.api_paper.native', return_value=[]), \
             patch('freqtrade.rpc.api_server.api_paper.paper_history.observe'):
            archived = archive_profile(profile['id'], self.config)
            self.assertTrue(archived['archived'])
            self.assertTrue(_paper_status(self.config)['profiles'][0]['archived'])
            with self.assertRaises(HTTPException) as blocked:
                start_paper(profile['id'], self.config)
            self.assertEqual(blocked.exception.status_code, 409)
        self.assertEqual((digest(folder / 'record.json'), digest(folder / 'config.json')), before)
        self.assertEqual(verify_profile(profile['id'], self.config)[1]['id'], profile['id'])
        self.assertFalse(restore_profile(profile['id'], self.config)['archived'])
        self.assertFalse(profile_visibility(profile['id'], self.config)['archived'])

    def test_worker_selected_profile_cannot_be_archived(self):
        profile = self.prepared()
        with patch('freqtrade.rpc.api_server.api_paper.checked_native',
                   return_value={'strategy': profile['wrapper']}):
            with self.assertRaises(HTTPException) as blocked:
                archive_profile(profile['id'], self.config)
        self.assertEqual(blocked.exception.status_code, 409)
        self.assertFalse(profile_visibility(profile['id'], self.config)['archived'])

    def test_native_resolver_keeps_archived_parameters_for_the_paper_wrapper(self):
        from freqtrade.resolvers import StrategyResolver
        profile = self.prepared()
        cfg, record = verify_profile(profile['id'], self.config)
        cfg['user_data_dir'] = Path(cfg['user_data_dir'])
        strategy = StrategyResolver.load_strategy(cfg)
        self.assertEqual(strategy.minimal_roi, {0:.07})
        self.assertEqual(strategy.stoploss, -.03)
        self.assertEqual(strategy.leverage(proposed_leverage=10), 1.0)

    def test_numeric_backtest_stake_string_is_converted_before_native_schema_validation(self):
        from freqtrade.rpc.api_server.api_paper import config_for, validate_recipe
        from freqtrade.rpc.api_server.api_runs import reproducible_config
        source = reproducible_config(self.config, {'stake_amount':'100'}, 'PaperSample')
        cfg = config_for(self.config, source, paper_root(self.config)/'numeric-test', 'FPPaperIdle', 'test')
        self.assertEqual(cfg['stake_amount'], 100.0)
        self.assertIsInstance(cfg['stake_amount'], float)
        with self.assertLogs('freqtrade.configuration.config_validation', level='CRITICAL'), self.assertRaises(HTTPException):
            validate_recipe({**cfg,'stake_amount':'100'})

    def test_open_positions_block_profile_change_without_touching_worker(self):
        profile = self.prepared()
        with patch('freqtrade.rpc.api_server.api_paper.checked_native', return_value={'strategy':'FPPaperIdle'}), \
             patch('freqtrade.rpc.api_server.api_paper.native', return_value=[{'trade_id': 1}]), \
             patch('freqtrade.rpc.api_server.api_paper.reload_stopped') as reload:
            with self.assertRaises(HTTPException): start_paper(profile['id'], self.config)
        reload.assert_not_called()

    def test_position_arriving_during_old_worker_shutdown_keeps_old_profile_paused(self):
        profile = self.prepared()
        with patch('freqtrade.rpc.api_server.api_paper.checked_native', return_value={'strategy':'FPPaperIdle'}), \
             patch('freqtrade.rpc.api_server.api_paper.native', side_effect=[[], [{'trade_id': 1}], {'status':'paused'}]) as api, \
             patch('freqtrade.rpc.api_server.api_paper.reload_stopped') as reload:
            with self.assertRaises(HTTPException): start_paper(profile['id'], self.config)
        self.assertEqual(reload.call_count, 1)
        self.assertEqual(reload.call_args[0][0]['strategy'], 'FPPaperIdle')
        self.assertEqual(api.call_args[0][:2], ('POST','/pause'))

    def test_successful_activation_uses_native_lifecycle_and_never_overwrites_main_config(self):
        profile = self.prepared()
        with patch('freqtrade.rpc.api_server.api_paper.checked_native', return_value={'strategy':'FPPaperIdle'}), \
             patch('freqtrade.rpc.api_server.api_paper.native', side_effect=[[], [], {'status':'starting'}]) as api, \
             patch('freqtrade.rpc.api_server.api_paper.reload_stopped') as reload, \
             patch('freqtrade.rpc.api_server.api_paper.paper_status', return_value={'online':True}):
            self.assertTrue(start_paper(profile['id'], self.config)['online'])
        self.assertEqual(reload.call_count, 2)
        self.assertEqual(reload.call_args[0][0]['strategy'], profile['wrapper'])
        self.assertEqual(api.call_args[0][:2], ('POST','/start'))
        self.assertFalse((self.base / 'config.json').exists())

    def test_stop_does_not_abandon_open_positions_and_wrong_service_is_rejected(self):
        with patch('freqtrade.rpc.api_server.api_paper.checked_native'), \
             patch('freqtrade.rpc.api_server.api_paper.native', return_value=[{'trade_id':1}]), \
             patch('freqtrade.rpc.api_server.api_paper.reload_stopped') as reload:
            with self.assertRaises(HTTPException):stop_paper(self.config)
        reload.assert_not_called()
        with patch('freqtrade.rpc.api_server.api_paper.native', return_value={'dry_run':False}):
            with self.assertRaises(HTTPException):checked_native(self.config)

    def test_local_helpers_are_reimported_when_switching_profiles(self):
        for number in (1, 2):
            folder = paper_root(self.config) / 'profiles' / str(number) / 'strategies'
            folder.mkdir(parents=True)
            (folder / 'fp_test_helper.py').write_text(f'value = {number}')
            (folder / 'HelperStrategy.py').write_text('from fp_test_helper import value\nclass HelperStrategy:\n    result = value\n')
            cls = load_paper_base('HelperStrategy', folder)
            self.assertEqual(cls.result, number)

    def test_restart_with_open_positions_recovers_exit_management_without_new_entries(self):
        profile = self.prepared()
        cfg, record = verify_profile(profile['id'], self.config)
        active = paper_root(self.config)/'active/config.json'
        write_check(active,cfg)
        database=Path(cfg['db_url'].removeprefix('sqlite:///'))
        with closing(sqlite3.connect(database)) as conn, conn:
            conn.execute('CREATE TABLE trades (is_open BOOLEAN)')
            conn.execute('INSERT INTO trades VALUES (1)')
        bootstrap(self.config)
        self.assertEqual(json.loads(active.read_text())['initial_state'],'paused')
        self.assertEqual(verify_profile(profile['id'],self.config)[0]['initial_state'],'stopped')
        with closing(sqlite3.connect(database)) as conn, conn:conn.execute('UPDATE trades SET is_open=0')
        bootstrap(self.config)
        self.assertEqual(json.loads(active.read_text())['initial_state'],'stopped')

    def test_native_paused_state_blocks_increases_but_keeps_partial_exits(self):
        from freqtrade.freqtradebot import FreqtradeBot
        from freqtrade.enums import State, ExitType
        trade=SimpleNamespace(pair='ETH/USDT:USDT',is_short=False,leverage=1,amount=1,
                              stake_amount=100,calc_profit_ratio=lambda rate:.1)
        exchange=SimpleNamespace(get_rates=lambda *args:(100,100),
            get_min_pair_stake_amount=lambda *args:1,get_max_pair_stake_amount=lambda *args:1000,
            amount_to_contract_precision=lambda pair,amount:amount)
        strategy=SimpleNamespace(stoploss=-.02,_adjust_trade_position_internal=Mock(return_value=(50,'increase')))
        bot=SimpleNamespace(state=State.PAUSED,exchange=exchange,strategy=strategy,
            wallets=SimpleNamespace(get_available_stake_amount=lambda:1000),
            execute_entry=Mock(),execute_trade_exit=Mock())
        FreqtradeBot.check_and_call_adjust_trade_position(bot,trade)
        bot.execute_entry.assert_not_called()
        bot.execute_trade_exit.assert_not_called()
        strategy._adjust_trade_position_internal.return_value=(-50,'partial-tp')
        FreqtradeBot.check_and_call_adjust_trade_position(bot,trade)
        bot.execute_trade_exit.assert_called_once()
        self.assertEqual(bot.execute_trade_exit.call_args.kwargs['sub_trade_amt'],.5)
        self.assertEqual(bot.execute_trade_exit.call_args.kwargs['exit_check'].exit_type,ExitType.PARTIAL_EXIT)


if __name__ == '__main__': unittest.main()
