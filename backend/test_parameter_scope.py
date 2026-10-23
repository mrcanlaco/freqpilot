"""Safety checks for native seed ownership and honest Parameter scope reporting."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from freqtrade.rpc.api_server import api_parameter_scope as seed
from freqtrade.rpc.api_server.api_runs import digest
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG


class FakeNative:
    pid = 123456
    returncode = 0

    def __init__(self, command, cwd):
        self.command = command
        self.cwd = cwd

    def wait(self, timeout=None):
        results = self.cwd / 'inputs/hyperopt_results'
        results.mkdir(exist_ok=True)
        current_seed = int(self.command[self.command.index('--random-state') + 1])
        row = {'fthypt_fileversion': 2, 'current_epoch': 1, 'loss': float(current_seed),
               'params_details': {'buy': {'buy_gate': current_seed}},
               'params_not_optimized': {},
               'results_metrics': {'total_trades': 2, 'profit_total_abs': 1.0,
                                   'profit_total': .001, 'max_drawdown_account': .01,
                                   'profit_factor': 1.2}}
        (results / 'native.fthypt').write_text(json.dumps(row) + '\n')
        return 0


class SeedChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        (self.base / 'strategies').mkdir()
        self.config = {'user_data_dir': self.base, 'datadir': self.base / 'data', 'dry_run': True}
        self.request = seed.SeedExperimentRequest(strategy='Sample', revision='a' * 64,
            settings={'timerange': '20260101-20260201', 'timeframe': '15m',
                      'timeframe_detail': '1m', 'dry_run_wallet': 1000,
                      'stake_amount': 100, 'max_open_trades': 2},
            epochs=2, spaces=['buy'], min_trades=1, seeds=[11, 23])
        self.cap = {'available': True, 'schema': {'revision': self.request.revision,
                     'parameter_revision': 'none', 'schema_revision': 'schema',
                     'fields': [{'name': 'buy_gate', 'space': 'buy', 'param_type': 'IntParameter',
                                 'low': 1, 'high': 50, 'value': 10, 'load': True, 'optimize': True}]},
                    'spaces': [{'id': 'buy', 'enabled': True}],
                    'losses': [{'id': 'SharpeHyperOptLossDaily'}]}
        self.old_active = seed._active_id
        self.old_owned = seed._owned.copy()
        self.old_opt_active = seed.opt._active_id
        self.old_analysis = ApiBG.analysis_running
        seed._active_id, seed._owned = None, {}
        seed.opt._active_id = None
        ApiBG.analysis_running = False

    def tearDown(self):
        seed._active_id, seed._owned = self.old_active, self.old_owned
        seed.opt._active_id = self.old_opt_active
        ApiBG.analysis_running = self.old_analysis
        self.temp.cleanup()

    def frozen(self, _manifest, _config):
        p = self.base / 'runs' / ('b' * 32)
        (p / 'inputs/strategies').mkdir(parents=True)
        (p / 'inputs/data').mkdir()
        (p / 'inputs/strategies/Sample.py').write_text('class Sample: pass\n')
        (p / 'inputs/data/BTC.feather').write_bytes(b'closed candles')
        config = {'strategy': 'Sample', 'dry_run': True, 'stake_amount': 100,
                  'dry_run_wallet': 1000, 'max_open_trades': 2,
                  'trading_mode': 'futures', 'margin_mode': 'isolated',
                  'exchange': {'name': 'binance', 'pair_whitelist': ['BTC/USDT:USDT']}}
        (p / 'inputs/config.json').write_text(json.dumps(config))
        files = {name: digest(p / name) for name in
                 ('inputs/strategies/Sample.py', 'inputs/data/BTC.feather', 'inputs/config.json')}
        frozen = {'files': files, 'config': config}
        (p / 'inputs.json').write_text(json.dumps(frozen))
        base = {'id': p.name, 'strategy': 'Sample', 'revision': self.request.revision,
                'engine': '2026.9', 'created_at': '2026-10-23T00:00:00+00:00',
                'settings': self.request.settings,
                'input_manifest_sha256': digest(p / 'inputs.json'),
                'input_files': len(files),
                'input_bytes': sum((p / name).stat().st_size for name in files)}
        return p, base

    def test_scope_reports_native_groups_and_refuses_per_parameter_override(self):
        with patch.object(seed.opt, 'capabilities', return_value=self.cap):
            result = seed.parameter_scope('Sample', self.config)
        self.assertFalse(result['per_parameter_override']['available'])
        self.assertEqual(result['parameters'][0]['high'], 50)
        self.assertEqual(result['native_spaces'][0]['id'], 'buy')

    def test_preview_rejects_duplicate_seed_and_excess_budget_without_child(self):
        with patch.object(seed.opt, 'capabilities', return_value=self.cap), \
             patch.object(seed, '_source_bytes', return_value=10), \
             patch.object(seed.subprocess, 'Popen') as launch:
            result = seed.preview(self.request, self.config)
            self.assertEqual(result['total_epochs'], 4)
            self.assertEqual(result['train_timerange'], '20260101-20260201')
            invalid = self.request.model_copy(update={'seeds': [11, 11]})
            with self.assertRaises(HTTPException):
                seed.preview(invalid, self.config)
            launch.assert_not_called()
        with patch.object(seed.opt, 'capabilities', return_value=self.cap), \
             patch.object(seed, '_source_bytes', return_value=seed.MAX_COPY_BYTES):
            with self.assertRaises(HTTPException):
                seed.preview(self.request, self.config)

    def test_each_seed_runs_in_distinct_native_snapshot_and_keeps_parent_guard(self):
        launches = []
        def launch(command, cwd, **_kwargs):
            launches.append((command, cwd, seed.opt._active_id, ApiBG.analysis_running))
            return FakeNative(command, cwd)
        with patch.object(seed.opt, 'capabilities', return_value=self.cap), \
             patch.object(seed.opt, 'ensure_idle'), \
             patch.object(seed, '_source_bytes', return_value=100), \
             patch.object(seed, 'freeze', side_effect=self.frozen), \
             patch.object(seed.opt, 'process_identity', return_value={'pid': FakeNative.pid, 'start_ticks': '1'}), \
             patch.object(seed.subprocess, 'Popen', side_effect=launch):
            accepted = seed.start(self.request, BackgroundTasks(), self.config)
            p = seed._path(accepted['id'], self.config)
            self.assertTrue(ApiBG.analysis_running)
            self.assertEqual(seed.get_experiment(accepted['id'], self.config)['status'], 'prepared')
            seed._run(p)
        result = seed.get_experiment(accepted['id'], self.config)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['completed_seeds'], 2)
        self.assertEqual([row['seed'] for row in result['results']], [11, 23])
        self.assertEqual([row['best_epoch']['loss'] for row in result['results']], [11.0, 23.0])
        self.assertEqual([row['seed'] for row in result['train_ranking']], [11, 23])
        self.assertEqual(len({cwd for _, cwd, _, _ in launches}), 2)
        self.assertTrue(all(owner == 'seed:' + accepted['id'] and flagged for _, _, owner, flagged in launches))
        self.assertTrue(all('--disable-param-export' in command for command, *_ in launches))
        self.assertFalse(ApiBG.analysis_running)

    def test_interrupted_owner_is_not_signalled_by_cancel(self):
        p, base = self.frozen(None, None)
        p = p.rename(seed._folder(self.config) / p.name)
        record = {'id': p.name, 'strategy': 'Sample', 'status': 'running',
                  'active_process_identity': None, 'active_command': None,
                  'created_at': base['created_at']}
        seed._persist(p, record)
        seen = seed.get_experiment(p.name, self.config)
        self.assertEqual(seen['status'], 'interrupted')
        with patch.object(seed.opt, 'stop_owned_group') as stop:
            seed.cancel(p.name, self.config)
            stop.assert_not_called()

    def test_cancel_signals_only_live_owned_seed_child(self):
        p, _ = self.frozen(None, None)
        p = p.rename(seed._folder(self.config) / p.name)
        seed._persist(p, {'id': p.name, 'strategy': 'Sample', 'status': 'running',
                          'active_process_identity': {'pid': FakeNative.pid, 'start_ticks': '1'},
                          'active_command': ['python', '-m', 'freqtrade'],
                          'cancel_requested_at': None})
        child = FakeNative(['python'], p)
        seed._active_id = p.name
        seed._owned[p.name] = child
        with patch.object(seed.opt, 'stop_owned_group') as stop:
            cancelled = seed.cancel(p.name, self.config)
        self.assertEqual(cancelled['status'], 'cancelling')
        self.assertTrue(cancelled['cancel_requested_at'])
        stop.assert_called_once()
        self.assertIs(stop.call_args.args[0], child)


if __name__ == '__main__':
    unittest.main()
