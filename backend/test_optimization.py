"""Native integration boundaries, without starting a Hyperopt/backtest/trade job."""
import asyncio
import json
import os
import signal
import subprocess
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request
from pydantic import ValidationError

from freqtrade.rpc.api_server import api_optimization as opt
from freqtrade.rpc.api_server.api_local_strategies import Create, create, read
from freqtrade.rpc.api_server.api_presets import inspect_parameters, load_preset, apply_preset
from freqtrade.rpc.api_server.api_studio import write_check
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG


class FakeProcess:
    pid = 678901
    returncode = None
    def poll(self): return self.returncode
    def wait(self, timeout=None):
        self.returncode = 0 if self.returncode is None else self.returncode
        return self.returncode


class OptimizationChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / 'strategies').mkdir()
        (self.base / 'data').mkdir()
        (self.base / 'data/BTC.feather').write_bytes(b'private frozen candle bytes')
        self.config = {'user_data_dir': self.base, 'datadir': self.base / 'data', 'dry_run': True,
                       'timeframe': '15m', 'dry_run_wallet': 1000, 'stake_amount': 100,
                       'stake_currency': 'USDT', 'max_open_trades': 2, 'trading_mode': 'futures',
                       'margin_mode': 'isolated', 'fee': .0005, 'pairlists': [{'method': 'StaticPairList'}],
                       'exchange': {'name': 'binance', 'pair_whitelist': ['BTC/USDT:USDT'],
                                    'key': 'MUST_NOT_COPY_TRADING_KEY'},
                       'api_server': {'password': 'MUST_NOT_COPY_API_PASSWORD'}}
        doc = create(Create(name='OptimizeSample'), self.config)
        source = doc['content'].replace('from freqtrade.strategy import IStrategy',
                                      'from freqtrade.strategy import IStrategy, IntParameter, DecimalParameter')
        source = source.replace('    INTERFACE_VERSION = 3', '''    buy_length = IntParameter(2, 40, default=10)
    sell_gate = DecimalParameter(.1, .9, default=.3, decimals=2)
    INTERFACE_VERSION = 3''')
        self.path = self.base / 'strategies/OptimizeSample.py'
        self.path.write_text(source)
        self.rev = read(self.path)['revision']
        self.settings = {'timeframe': '15m', 'timeframe_detail': '1m', 'timerange': '20260918-20261022',
                         'dry_run_wallet': 1000, 'stake_amount': 100, 'max_open_trades': 2,
                         'enable_protections': False}
        self.old_active, self.old_processes = opt._active_id, opt._processes.copy()
        opt._active_id, opt._processes = None, {}
        self.bg = patch.object(ApiBG, 'analysis_running', False)
        self.dl = patch.object(ApiBG, 'download_data_running', False)
        self.bg.start()
        self.dl.start()

    def tearDown(self):
        opt._active_id, opt._processes = self.old_active, self.old_processes
        self.bg.stop()
        self.dl.stop()
        self.tmp.cleanup()

    def request(self, **changes):
        return opt.OptimizationStart(**{'strategy': 'OptimizeSample', 'revision': self.rev,
            'settings': self.settings, 'epochs': 4, 'spaces': ['buy'], 'min_trades': 2,
            'validation': 'split', 'split_date': '20261010', **changes})

    def start(self, **changes):
        self.process = FakeProcess()
        self.tasks = BackgroundTasks()
        with patch('freqtrade.rpc.api_server.api_runs.manifest', return_value={'id': 'preflight'}), \
             patch.object(opt.subprocess, 'Popen', return_value=self.process) as popen, \
             patch.object(opt, 'process_identity', return_value={'pid': self.process.pid, 'start_ticks': '42'}):
            result = asyncio.run(opt.start_optimization(self.request(**changes), self.tasks, self.config))
            self.launch = popen.call_args
        self.folder = opt.optimization_path(result['id'], self.config)
        return result

    def row(self, epoch=1, loss=-1, trades=3, buy=18):
        return {'fthypt_fileversion': 2, 'current_epoch': epoch, 'loss': loss,
                'params_details': {'buy': {'buy_length': buy}},
                'params_not_optimized': {'sell': {'sell_gate': .3}, 'roi': {'0': .04},
                                        'stoploss': {'stoploss': -.02},
                                        'trailing': {'trailing_stop': False, 'trailing_stop_positive': None,
                                                     'trailing_stop_positive_offset': 0.0,
                                                     'trailing_only_offset_is_reached': False},
                                        'max_open_trades': {'max_open_trades': 2}},
                'results_metrics': {'total_trades': trades, 'profit_total_abs': 5,
                                    'profit_total': .005, 'max_drawdown_account': .01, 'profit_factor': 1.2}}

    def result_file(self, rows):
        path = self.folder / 'inputs/hyperopt_results/native.fthypt'
        path.write_text(''.join(json.dumps(row) + '\n' for row in rows))
        return path

    def completed(self, rows=None):
        record = self.start()
        self.result_file(rows or [self.row()])
        self.process.returncode = 0
        opt.finish_process(self.folder, self.process)
        return opt.get_optimization(record['id'], self.config)

    def test_native_capabilities_block_unloadable_groups_and_config_overrides(self):
        cap = opt.capabilities('OptimizeSample', self.config)
        self.assertTrue(cap['available'])
        self.assertTrue(next(r for r in cap['spaces'] if r['id'] == 'buy')['enabled'])
        self.path.write_text(self.path.read_text().replace('    INTERFACE_VERSION = 3',
            '    buy_locked = IntParameter(1, 5, default=2, load=False)\n    INTERFACE_VERSION = 3'))
        self.config.update(stoploss=-.03, minimal_roi={'0': .05}, trailing_stop=False)
        cap = opt.capabilities('OptimizeSample', self.config)
        groups = {r['id']: r for r in cap['spaces']}
        for space in ('buy', 'stoploss', 'roi', 'trailing'):
            self.assertFalse(groups[space]['enabled'])
            self.assertTrue(groups[space]['reason'])

    def test_bounds_loss_space_stale_source_and_bad_splits_never_launch(self):
        for changes in ({'epochs': 0}, {'epochs': 501}, {'workers': 3}, {'random_state': 0}, {'min_trades': 0}):
            with self.subTest(changes=changes), self.assertRaises(ValidationError): self.request(**changes)
        for changes in ({'loss': 'MyCustomLoss'}, {'spaces': ['all']}, {'spaces': ['buy', 'buy']},
                        {'revision': 'old'}, {'split_date': '2026-09-18'}, {'split_date': '2026-10-22'},
                        {'split_date': 'not-a-date'}, {'settings': {**self.settings, 'timerange': '20260918-'}}):
            with self.subTest(changes=changes), patch.object(opt.subprocess, 'Popen') as launch, self.assertRaises(HTTPException):
                asyncio.run(opt.start_optimization(self.request(**changes), BackgroundTasks(), self.config))
                launch.assert_not_called()

    def test_native_forced_protection_and_sell_exit_signal_cannot_change_protocol_silently(self):
        self.path.write_text(self.path.read_text().replace('    INTERFACE_VERSION = 3',
            '    use_exit_signal = False\n    protection_guard = IntParameter(1, 5, default=2, space="protection")\n    INTERFACE_VERSION = 3'))
        groups = {r['id']: r for r in opt.capabilities('OptimizeSample', self.config)['spaces']}
        self.assertFalse(groups['sell']['enabled'])
        self.assertFalse(groups['protection']['enabled'])
        self.assertTrue(groups['sell']['reason'])
        self.assertTrue(groups['protection']['reason'])

    def test_child_is_native_cli_private_config_train_only_no_env_override_or_source_edit(self):
        before = self.path.read_bytes()
        with patch.dict(os.environ, {'FREQTRADE__EXCHANGE__KEY': 'DO_NOT_INHERIT', 'FREQTRADE__DRY_RUN': 'false'}):
            record = self.start()
        command = self.launch.args[0]
        self.assertEqual(command[3], 'hyperopt')
        for flag in ('--disable-param-export', '--analyze-per-epoch', '--job-workers', '--random-state'):
            self.assertIn(flag, command)
        from freqtrade.commands.arguments import Arguments
        parsed = Arguments(command[3:]).get_parsed_arg()
        self.assertTrue(parsed['disableparamexport'])
        self.assertTrue(parsed['analyze_per_epoch'])
        self.assertEqual(parsed['hyperopt_jobs'], 1)
        runtime = json.loads((self.folder / 'runtime.json').read_text())
        self.assertEqual(runtime['timerange'], '20260918-20261010')
        self.assertEqual(record['oos_timerange'], '20261010-20261022')
        self.assertTrue(runtime['dry_run'])
        self.assertNotIn('api_server', runtime)
        self.assertNotIn('key', runtime['exchange'])
        self.assertNotIn('DO_NOT_INHERIT', json.dumps(self.launch.kwargs['env']))
        self.assertNotIn('FREQTRADE__DRY_RUN', self.launch.kwargs['env'])
        self.assertTrue(self.launch.kwargs['start_new_session'])
        self.assertEqual(self.launch.kwargs['cwd'], self.folder)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(self.path.with_suffix('.json').exists())
        self.assertTrue(ApiBG.analysis_running)
        self.assertEqual(list((self.base / 'freqpilot/runs').glob('*/record.json')), [])

    def test_active_native_or_download_job_refuses_optimization_and_no_new_process(self):
        for name in ('analysis_running', 'download_data_running'):
            with self.subTest(flag=name), patch.object(ApiBG, name, True), patch.object(opt.subprocess, 'Popen') as launch:
                with self.assertRaises(HTTPException):
                    asyncio.run(opt.start_optimization(self.request(), BackgroundTasks(), self.config))
                launch.assert_not_called()
        self.start()
        with patch.object(opt.subprocess, 'Popen') as launch:
            with self.assertRaises(HTTPException):
                asyncio.run(opt.start_optimization(self.request(), BackgroundTasks(), self.config))
            launch.assert_not_called()

    def test_ui_numeric_strings_are_normalized_for_cli_but_frozen_request_is_retained(self):
        settings = {**self.settings, 'stake_amount': '100.25', 'dry_run_wallet': '1000.50', 'max_open_trades': '2'}
        self.start(settings=settings)
        runtime = json.loads((self.folder / 'runtime.json').read_text())
        self.assertEqual(runtime['stake_amount'], 100.25)
        self.assertIsInstance(runtime['stake_amount'], float)
        self.assertEqual(runtime['dry_run_wallet'], 1000.5)
        self.assertIsInstance(runtime['dry_run_wallet'], float)
        self.assertEqual(runtime['max_open_trades'], 2)
        self.assertIsInstance(runtime['max_open_trades'], int)
        from jsonschema import validate
        from freqtrade.config_schema.config_schema import CONF_SCHEMA
        for field in ('stake_amount', 'dry_run_wallet', 'max_open_trades'):
            validate(runtime[field], CONF_SCHEMA['properties'][field])
        frozen = json.loads((self.folder / 'inputs.json').read_text())
        self.assertEqual(frozen['settings']['stake_amount'], '100.25')
        self.assertEqual(frozen['config']['stake_amount'], '100.25')
        self.assertEqual(opt.digest(self.folder / 'runtime.json'), json.loads((self.folder / 'record.json').read_text())['runtime_sha256'])

    def test_legacy_native_controls_cannot_abort_or_overlap_active_optimization(self):
        self.start()
        for method, path in [('POST', '/api/v1/backtest'), ('DELETE', '/api/v1/backtest'), ('GET', '/api/v1/backtest'),
                             ('GET', '/api/v1/backtest/abort'), ('POST', '/api/v1/download_data'),
                             ('POST', '/api/v1/lookahead_analysis'), ('POST', '/api/v1/recursive_analysis')]:
            request = Request({'type': 'http', 'method': method, 'path': path, 'headers': []})
            with self.subTest(path=path), self.assertRaises(HTTPException): opt.guard_native_research(request)
        request = Request({'type': 'http', 'method': 'GET', 'path': '/api/v1/backtest/history', 'headers': []})
        opt.guard_native_research(request)

    def test_streaming_progress_sort_paging_nonfinite_and_min_trade_eligibility(self):
        record = self.start()
        path = self.result_file([self.row(1, -5, trades=1), self.row(2, 0), self.row(3, -2), self.row(4, float('nan'))])
        with path.open('ab') as stream: stream.write(b'{"partial":')
        result = opt.list_epochs(record['id'], offset=0, limit=2, sort='loss', config=self.config)
        self.assertEqual(result['total'], 4)
        self.assertEqual([r['epoch'] for r in result['epochs']], [3, 2])
        rows = opt.list_epochs(record['id'], 0, 50, 'epoch', self.config)['epochs']
        self.assertFalse(rows[0]['eligible'])
        self.assertIsNone(rows[-1]['loss'])
        self.assertFalse(rows[-1]['eligible'])
        status = opt.get_optimization(record['id'], self.config)
        self.assertEqual(status['completed_epochs'], 4)
        self.assertEqual(status['best_epoch']['epoch'], 3)
        with self.assertRaises(HTTPException): opt.list_epochs(record['id'], -1, 50, 'loss', self.config)

    def test_completed_process_releases_engine_keeps_hashes_and_detects_tampering(self):
        record = self.completed()
        self.assertEqual(record['status'], 'success')
        self.assertTrue(record['result_sha256'])
        self.assertFalse(ApiBG.analysis_running)
        self.assertIsNone(opt._active_id)
        self.assertEqual(record['best_epoch']['epoch'], 1)
        with (self.folder / 'inputs/hyperopt_results/native.fthypt').open('ab') as stream: stream.write(b'{}\n')
        with self.assertRaises(HTTPException): opt.list_epochs(record['id'], config=self.config)

    def test_missing_handle_becomes_interrupted_and_never_signals_pid_only(self):
        record = self.start()
        opt._processes.clear()
        opt._active_id = None
        ApiBG.analysis_running = False
        with patch.object(opt, 'orphan_alive', return_value=False), patch.object(os, 'killpg') as kill:
            status = opt.get_optimization(record['id'], self.config)
            self.assertEqual(status['status'], 'interrupted')
            self.assertFalse(status['orphan_process_alive'])
            opt.cancel_optimization(record['id'], BackgroundTasks(), self.config)
            kill.assert_not_called()

    def test_orphan_with_exact_native_identity_blocks_new_jobs(self):
        record = self.start()
        opt._processes.clear()
        opt._active_id = None
        ApiBG.analysis_running = False
        with patch.object(opt, 'orphan_alive', return_value=True), patch.object(opt.subprocess, 'Popen') as launch:
            status = opt.get_optimization(record['id'], self.config)
            self.assertTrue(status['orphan_process_alive'])
            with self.assertRaises(HTTPException):
                asyncio.run(opt.start_optimization(self.request(), BackgroundTasks(), self.config))
            launch.assert_not_called()

    def test_interrupted_orphan_block_is_retired_after_child_exits_without_claiming_success(self):
        record = self.start()
        opt._processes.clear()
        opt._active_id = None
        ApiBG.analysis_running = False
        with patch.object(opt, 'orphan_alive', return_value=True):
            first = opt.get_optimization(record['id'], self.config)
            self.assertEqual(first['status'], 'interrupted')
            self.assertTrue(first['orphan_process_alive'])
        with patch.object(opt, 'orphan_alive', return_value=False):
            later = opt.get_optimization(record['id'], self.config)
            self.assertEqual(later['status'], 'interrupted')
            self.assertFalse(later['orphan_process_alive'])
            self.assertEqual(later['finished_at'], first['finished_at'])
            self.assertIsNone(later['result_sha256'])
            opt.ensure_idle(self.config)
        self.assertFalse(json.loads((self.folder / 'record.json').read_text())['orphan_process_alive'])

    def test_cancel_targets_exact_live_owned_group_and_preserves_cancelled_status(self):
        record = self.start()
        self.result_file([self.row()])
        with patch.object(os, 'getpgid', return_value=self.process.pid), patch.object(os, 'killpg') as kill:
            result = opt.cancel_optimization(record['id'], BackgroundTasks(), self.config)
            self.assertEqual(result['status'], 'cancelling')
            opt.cancel_optimization(record['id'], BackgroundTasks(), self.config)
            kill.assert_called_once_with(self.process.pid, signal.SIGINT)
        self.process.returncode = 0  # native catches Ctrl+C; zero is still cancellation
        opt.finish_process(self.folder, self.process)
        status = opt.get_optimization(record['id'], self.config)
        self.assertEqual(status['status'], 'cancelled')
        self.assertEqual(status['completed_epochs'], 1)
        self.assertFalse(ApiBG.analysis_running)

    def test_cancellation_cannot_signal_foreign_or_finished_process(self):
        record = self.start()
        with patch.object(os, 'getpgid', return_value=1), patch.object(os, 'killpg') as kill:
            opt.cancel_optimization(record['id'], BackgroundTasks(), self.config)
            kill.assert_not_called()
        self.process.returncode = 0
        with patch.object(os, 'killpg') as kill:
            opt.stop_owned_group(self.process, signal.SIGTERM)
            kill.assert_not_called()

    def test_native_failure_no_results_and_tampered_runtime_are_not_success(self):
        for kind in ('exit', 'empty', 'runtime', 'inputs', 'partial'):
            with self.subTest(kind=kind):
                record = self.start()
                if kind != 'empty': self.result_file([self.row()])
                if kind == 'runtime': (self.folder / 'runtime.json').write_text('{}')
                if kind == 'inputs': (self.folder / 'inputs/data/BTC.feather').write_bytes(b'changed')
                if kind == 'partial':
                    with (self.folder / 'inputs/hyperopt_results/native.fthypt').open('ab') as stream: stream.write(b'{')
                self.process.returncode = 1 if kind == 'exit' else 0
                opt.finish_process(self.folder, self.process)
                result = opt.get_optimization(record['id'], self.config)
                self.assertEqual(result['status'], 'failed')
                self.assertFalse(ApiBG.analysis_running)

    def test_promotion_uses_native_json_full_groups_and_does_not_touch_library(self):
        record = self.completed()
        source = self.path.read_bytes()
        saved = opt.promote_epoch(record['id'], 1, opt.EpochPreset(label='Ứng viên 1'), self.config)
        _, path = load_preset('OptimizeSample', saved['id'], self.config)
        params = json.loads(path.read_text())['params']
        self.assertEqual(params['buy']['buy_length'], 18)
        self.assertEqual(params['roi'], {'0': .04})
        self.assertEqual(params['stoploss'], {'stoploss': -.02})
        self.assertIsNone(params['trailing']['trailing_stop_positive'])
        self.assertEqual(saved['optimization']['train_timerange'], record['train_timerange'])
        self.assertEqual(saved['optimization']['spaces'], ['buy'])
        self.assertEqual(self.path.read_bytes(), source)
        self.assertFalse(self.path.with_suffix('.json').exists())
        private = self.base / 'apply'
        (private / 'strategies').mkdir(parents=True)
        (private / 'strategies/OptimizeSample.py').write_bytes(source)
        apply_preset('OptimizeSample', saved['id'], private, self.config)
        self.assertEqual((private / 'strategies/OptimizeSample.json').read_bytes(), path.read_bytes())

    def test_stale_library_blocks_promotion_but_frozen_candidate_validation_remains_available(self):
        record = self.completed()
        (self.config['datadir'] / 'BTC.feather').write_bytes(b'new live data')
        self.path.write_text('# deleted live strategy class')
        self.config.update(fee=.9, stoploss=-.9, minimal_roi={'0': 9}, freqai={'enabled': True})
        self.config['exchange']['pair_whitelist'] = ['ETH/USDT:USDT']
        with self.assertRaises(HTTPException):
            opt.promote_epoch(record['id'], 1, opt.EpochPreset(label='stale'), self.config)
        captured = {}
        async def launch(p, result, tasks, cfg, runtime):
            captured.update(p=p, record=result, runtime=runtime)
            return result
        with patch.object(opt, 'launch_snapshot', side_effect=launch):
            result = asyncio.run(opt.validate_epoch(record['id'], 1, opt.EpochValidation(mode='oos'), BackgroundTasks(), self.config))
        p = captured['p']
        self.assertEqual((p / 'inputs/data/BTC.feather').read_bytes(), b'private frozen candle bytes')
        self.assertIn('class OptimizeSample', (p / 'inputs/strategies/OptimizeSample.py').read_text())
        self.assertEqual(result['settings']['timerange'], '20261010-20261022')
        self.assertEqual(captured['runtime']['fee'], .0005)
        self.assertNotIn('freqai', captured['runtime'])
        self.assertNotIn('minimal_roi', captured['runtime'])
        self.assertNotIn('api_server', captured['runtime'])
        self.assertEqual(captured['runtime']['exchange']['pair_whitelist'], ['BTC/USDT:USDT'])
        recipe = json.loads((p / 'inputs.json').read_text())
        self.assertEqual(recipe['optimization']['mode'], 'oos')
        self.assertEqual(recipe['optimization']['result_sha256'], record['result_sha256'])
        self.assertNotIn('preset', recipe)
        self.assertEqual(json.loads((p / 'inputs/strategies/OptimizeSample.json').read_text())['params']['buy']['buy_length'], 18)

    def test_new_config_override_blocks_builtin_epoch_promotion(self):
        record = self.start(spaces=['roi'])
        row = self.row()
        row['params_details'] = {'roi': {'0': .06}}
        row['params_not_optimized'].pop('roi')
        row['params_not_optimized']['buy'] = {'buy_length': 10}
        self.result_file([row])
        self.process.returncode = 0
        opt.finish_process(self.folder, self.process)
        self.config['minimal_roi'] = {'0': .9}
        with self.assertRaises(HTTPException):
            opt.promote_epoch(record['id'], 1, opt.EpochPreset(label='overridden'), self.config)

    def test_ineligible_unknown_active_and_tampered_epochs_never_promote_or_validate(self):
        record = self.completed([self.row(trades=1)])
        with self.assertRaises(HTTPException): opt.promote_epoch(record['id'], 1, opt.EpochPreset(label='bad'), self.config)
        with self.assertRaises(HTTPException): opt.promote_epoch(record['id'], 9, opt.EpochPreset(label='missing'), self.config)
        with self.assertRaises(HTTPException):
            asyncio.run(opt.validate_epoch(record['id'], 1, opt.EpochValidation(mode='train'), BackgroundTasks(), self.config))
        self.start()
        with self.assertRaises(HTTPException): opt.promote_epoch(record['id'], 1, opt.EpochPreset(label='busy'), self.config)

    def test_single_range_has_no_oos_and_both_split_formats_match(self):
        self.assertEqual(opt.ranges(self.request(split_date='2026-10-10')), opt.ranges(self.request()))
        self.assertEqual(opt.ranges(self.request(validation='single', split_date=None)), ('20260918-20261022', None))
        record = self.completed()
        row = json.loads((self.folder / 'record.json').read_text())
        row['oos_timerange'] = None
        write_check(self.folder / 'record.json', row)
        with self.assertRaises(HTTPException):
            asyncio.run(opt.validate_epoch(record['id'], 1, opt.EpochValidation(mode='oos'), BackgroundTasks(), self.config))


if __name__ == '__main__': unittest.main()
