"""Offline checks for WFA boundaries, ownership, and train-only selection."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from pydantic import ValidationError

from freqtrade.rpc.api_server import api_walk_forward as wfa
from freqtrade.rpc.api_server import api_optimization as opt
from freqtrade.rpc.api_server.api_studio import write_check
from freqtrade.rpc.api_server.api_runs import digest
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG


class RequestChecks(unittest.TestCase):
    def setUp(self):
        self.req = {'strategy': 'Sample', 'revision': 'abc',
                    'settings': {'timerange': '20260101-20260501', 'enable_protections': False},
                    'epochs': 10, 'spaces': ['buy'], 'train_days': 30,
                    'oos_days': 10, 'gap_days': 2, 'holdout_days': 20,
                    'max_windows': 6}

    def model(self, **updates):
        return wfa.WalkForwardRequest(**{**self.req, **updates})

    def test_rolling_timeline_nonoverlap_gap_and_sealed_holdout(self):
        windows, holdout = wfa.timeline(self.model())
        self.assertEqual(holdout, '20260411-20260501')
        self.assertEqual(len(windows), 6)
        self.assertEqual(windows[0]['train_timerange'], '20260101-20260131')
        self.assertEqual(windows[0]['oos_timerange'], '20260202-20260212')
        for left, right in zip(windows, windows[1:]):
            self.assertEqual(left['oos_timerange'].split('-')[1], right['oos_timerange'].split('-')[0])
            self.assertLessEqual(right['oos_timerange'].split('-')[1], holdout.split('-')[0])
            train_end = left['train_timerange'].split('-')[1]
            oos_start = left['oos_timerange'].split('-')[0]
            self.assertLess(train_end, oos_start)

    def test_rejects_truncated_or_invalid_protocol(self):
        with self.assertRaisesRegex(HTTPException, 'vượt giới hạn'):
            wfa.timeline(self.model(max_windows=2))
        with self.assertRaisesRegex(HTTPException, 'hai cửa sổ'):
            wfa.timeline(self.model(settings={'timerange': '20260101-20260305'}, holdout_days=20))
        for raw in ('20260101-', '20260230-20260501', '20260501-20260101'):
            with self.subTest(raw=raw), self.assertRaises(HTTPException):
                wfa.timeline(self.model(settings={'timerange': raw}))
        with self.assertRaises(ValidationError):
            self.model(epochs=0)

    def test_preview_budget_is_bounded_and_never_launches(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            base.joinpath('BTC.feather').write_bytes(b'one')
            caps = {'available': True, 'schema': {'revision': 'abc', 'schema_revision': 'schema'},
                    'spaces': [{'id': 'buy', 'enabled': True}],
                    'losses': [{'id': 'SharpeHyperOptLossDaily'}]}
            config = {'datadir': base, 'user_data_dir': base,
                      'exchange': {'name': 'binance'}}
            with patch.object(wfa, 'capabilities', return_value=caps), \
                 patch.object(wfa, 'normalize_cli_numbers', side_effect=lambda value: value), \
                 patch('freqtrade.rpc.api_server.api_runs.reproducible_config', return_value={}):
                result = wfa.preview(self.model(), config)
            self.assertEqual(result['estimated_input_bytes'], 3 * 7)
            self.assertEqual(result['estimated_hyperopt_epochs'], 60)
            self.assertEqual(result['estimated_backtests'], 14)


class OwnershipChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / 'strategies').mkdir()
        self.config = {'user_data_dir': self.base, 'datadir': self.base, 'dry_run': True}
        self.old_active = wfa._active_id
        self.old_opt_active = opt._active_id
        wfa._active_id = None
        opt._active_id = None
        self.analysis = patch.object(ApiBG, 'analysis_running', False)
        self.analysis.start()

    def tearDown(self):
        wfa._active_id = self.old_active
        opt._active_id = self.old_opt_active
        self.analysis.stop()
        self.tmp.cleanup()

    def record(self, status='running'):
        uid = 'a' * 32
        p = wfa.root(self.config) / uid
        p.mkdir(exist_ok=True)
        item = {'id': uid, 'strategy': 'Sample', 'status': status, 'windows': [],
                'active_command': ['python', '-m', 'freqtrade'],
                'active_process_identity': {'pid': 123, 'start_ticks': '4'}}
        write_check(p / 'record.json', item)
        return p, item

    def test_restart_marks_interrupted_without_killing_persisted_pid(self):
        p, item = self.record()
        with patch.object(wfa, '_orphan_alive', return_value=True):
            refreshed = wfa.get_walk_forward(item['id'], self.config)
            self.assertEqual(refreshed['status'], 'interrupted')
            self.assertTrue(refreshed['orphan_process_alive'])
            with self.assertRaises(HTTPException):
                wfa.guard_wfa_orphans(self.config)
            self.assertEqual(wfa.cancel(item['id'], BackgroundTasks(), self.config)['status'], 'interrupted')
        with patch.object(wfa, '_orphan_alive', return_value=False):
            refreshed = wfa.get_walk_forward(item['id'], self.config)
            self.assertFalse(refreshed['orphan_process_alive'])
            wfa.guard_wfa_orphans(self.config)
        self.assertEqual(json.loads((p / 'record.json').read_text())['status'], 'interrupted')

    def test_cancel_signals_only_exact_owned_child(self):
        p, item = self.record()
        class Child:
            pid = 234
            def poll(self): return None
        child = Child()
        wfa._active_id = item['id']
        wfa._owned[item['id']] = child
        try:
            with patch.object(wfa, 'stop_owned_group') as stop:
                answer = wfa.cancel(item['id'], BackgroundTasks(), self.config)
                self.assertEqual(answer['status'], 'cancelling')
                stop.assert_called_once_with(child, wfa.signal.SIGINT)
                self.assertTrue(json.loads((p / 'record.json').read_text())['cancel_requested_at'])
        finally:
            wfa._owned.pop(item['id'], None)

    def test_cancel_before_child_launch_does_not_start_new_native_process(self):
        p, item = self.record('cancelling')
        item['cancel_requested_at'] = '2026-01-01T00:00:00+00:00'
        write_check(p / 'record.json', item)
        local = {**item, 'cancel_requested_at': None}
        with patch.object(wfa.subprocess, 'Popen') as launch:
            result = wfa._child(p, local, ['python', '-m', 'freqtrade'], 'window:1:hyperopt')
        self.assertFalse(result)
        launch.assert_not_called()
        self.assertEqual(local['status'], 'cancelling')

    def test_holdout_uses_latest_train_winner_without_oos_reranking(self):
        p, item = self.record('success')
        item.update(holdout_status='sealed', holdout_timerange='20260411-20260501',
                    windows=[{'index': 0, 'candidate': {'status': 'success', 'summary': {'profit_total_abs': 900}},
                              'hyperopt': {'status': 'success', 'best_epoch': {'epoch': 1, 'eligible': True}}},
                             {'index': 1, 'candidate': {'status': 'failed', 'summary': {'profit_total_abs': -20}},
                              'hyperopt': {'status': 'success', 'best_epoch': {'epoch': 4, 'eligible': True}}}])
        write_check(p / 'record.json', item)
        with patch.object(wfa, '_ensure_idle'), patch.object(wfa, '_reserve'):
            result = wfa.evaluate_holdout(item['id'], BackgroundTasks(), self.config)
        self.assertEqual(result['holdout_selection']['window'], 1)
        self.assertEqual(result['holdout_selection']['epoch'], 4)
        self.assertEqual(result['holdout_attempts'], 1)
        self.assertEqual(result['holdout_status'], 'running')

    def test_runner_hyperopts_train_only_and_backtests_each_disjoint_oos(self):
        p, item = self.record('prepared')
        source = p / 'inputs/strategies/Sample.py'
        source.parent.mkdir(parents=True)
        source.write_text('class Sample: pass')
        config_file = p / 'inputs/config.json'
        config_file.write_text('{}')
        inventory = {'inputs/strategies/Sample.py': digest(source),
                     'inputs/config.json': digest(config_file)}
        frozen = {'config': {'strategy': 'Sample'}, 'files': inventory}
        (p / 'inputs.json').write_text(json.dumps(frozen))
        item.update(revision=digest(source), input_manifest_sha256=digest(p / 'inputs.json'),
                    epochs=3, spaces=['buy'], loss='SharpeHyperOptLossDaily',
                    random_state=42, min_trades=1, workers=1,
                    completed_windows=0, cancel_requested_at=None, schema={'fields': []},
                    windows=[{'index': 0, 'train_timerange': '20260101-20260111',
                              'oos_timerange': '20260112-20260117', 'status': 'pending',
                              'baseline': None, 'candidate': None, 'hyperopt': None},
                             {'index': 1, 'train_timerange': '20260106-20260116',
                              'oos_timerange': '20260117-20260122', 'status': 'pending',
                              'baseline': None, 'candidate': None, 'hyperopt': None}])
        write_check(p / 'record.json', item)
        hyper_ranges, backtests = [], []
        row = {'fthypt_fileversion': 2, 'current_epoch': 1, 'loss': -1,
               'params_details': {'buy': {'length': 10}}, 'params_not_optimized': {},
               'results_metrics': {'total_trades': 3, 'profit_total_abs': 4}}

        def fake_child(base, record, command, stage):
            self.assertEqual(base, p)
            self.assertIn(':hyperopt', stage)
            path = Path(command[command.index('--config') + 1])
            hyper_ranges.append(json.loads(path.read_text())['timerange'])
            return True

        def fake_backtest(target, record, base, timerange, variant, row=None):
            backtests.append((timerange, variant, row is not None))
            return {'status': 'success', 'summary': {'profit_total_abs': 1 if row else 0}}

        with patch.object(wfa, '_child', side_effect=fake_child), \
             patch.object(wfa, '_backtest', side_effect=fake_backtest), \
             patch.object(wfa, 'epoch_rows', return_value=[row]), \
             patch.object(opt, 'epoch_values', return_value={}), \
             patch.object(wfa, 'normalize_cli_numbers', side_effect=lambda value: value):
            wfa._run_windows(p, self.config)
        final = json.loads((p / 'record.json').read_text())
        self.assertEqual(final['status'], 'success')
        self.assertEqual(final['research_status'], 'review')
        self.assertEqual(final['incomplete_windows'], 0)
        self.assertEqual(hyper_ranges, ['20260101-20260111', '20260106-20260116'])
        self.assertEqual(backtests, [('20260112-20260117', 'baseline', False),
                                     ('20260112-20260117', 'candidate', True),
                                     ('20260117-20260122', 'baseline', False),
                                     ('20260117-20260122', 'candidate', True)])
        self.assertEqual(final['completed_windows'], 2)


if __name__ == '__main__':
    unittest.main()
