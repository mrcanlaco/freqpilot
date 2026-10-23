"""Offline checks for matrix preflight, isolated cells, and child ownership."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException

from freqtrade.rpc.api_server import api_matrix as matrix
from freqtrade.rpc.api_server import api_optimization as opt
from freqtrade.rpc.api_server.api_studio import write_check
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG


class MatrixChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / 'data').mkdir()
        self.config = {'user_data_dir': self.base, 'datadir': self.base / 'data',
                       'exchange': {'name': 'binance', 'pair_whitelist': ['BTC/USDT:USDT', 'ETH/USDT:USDT']},
                       'dry_run': True}
        self.req = matrix.MatrixRequest(strategy='Sample', revision='a' * 64,
            settings={'timerange': '20260101-20260201', 'timeframe_detail': '1m',
                      'dry_run_wallet': 1000, 'stake_amount': 100, 'max_open_trades': 2},
            pairs=['BTC/USDT:USDT', 'ETH/USDT:USDT'], timeframes=['15m', '1h'])
        self.old_active, self.old_opt_active = matrix._active_id, opt._active_id
        matrix._active_id = opt._active_id = None
        self.analysis = patch.object(ApiBG, 'analysis_running', False)
        self.analysis.start()

    def tearDown(self):
        matrix._active_id, opt._active_id = self.old_active, self.old_opt_active
        matrix._owned.clear()
        self.analysis.stop()
        self.tmp.cleanup()

    def test_preview_reports_each_cell_and_blocks_unknown_funding(self):
        reports = []
        def quality(config, timerange, frame, detail, warmup, verify_funding, persist):
            pair = config['exchange']['pair_whitelist'][0]
            reports.append((pair, frame, verify_funding, persist))
            status = 'unknown' if pair.startswith('ETH') and frame == '1h' else 'ok'
            return {'status': status, 'issues': [{'severity': 'unknown', 'code': 'funding_api_unavailable'}] if status != 'ok' else [],
                    'dataset_sha256': f'{pair}-{frame}', 'files': [], 'funding_verification': {'status': status}}
        with patch.object(matrix, '_validate', return_value=200), \
             patch.object(matrix, 'quality_report', side_effect=quality), \
             patch('freqtrade.rpc.api_server.api_studio.manifest', return_value={'id': 'preflight'}) as manifest:
            answer = matrix.preview(self.req, self.config)
        self.assertEqual(answer['estimated_runs'], 4)
        self.assertFalse(answer['ready'])
        self.assertEqual(len(manifest.call_args_list), 3)
        self.assertEqual({(p, f) for p, f, _, _ in reports},
                         {(p, f) for p in self.req.pairs for f in self.req.timeframes})
        self.assertTrue(all(remote and not persist for _, _, remote, persist in reports))
        self.assertEqual(answer['cells'][-1]['funding_verification'], 'unknown')

    def test_rejects_duplicate_or_unsupported_cells_and_ambiguous_frame(self):
        with self.assertRaises(HTTPException):
            matrix._validate(self.req.model_copy(update={'pairs': ['BTC/USDT:USDT'] * 2}), self.config)
        with self.assertRaises(HTTPException):
            matrix._validate(self.req.model_copy(update={'timeframes': ['7m']}), self.config)
        with self.assertRaises(HTTPException):
            matrix._validate(self.req.model_copy(update={'settings': {**self.req.settings, 'timeframe': '15m'}}), self.config)

    def test_warmup_must_be_integer_literal(self):
        with patch.object(matrix, 'target', return_value=self.base / 'Sample.py'), \
             patch.object(matrix, 'read', return_value={'revision': self.req.revision,
                                                        'content': 'class Sample:\n    startup_candle_count = 0.5\n'}):
            with self.assertRaisesRegex(HTTPException, 'startup_candle_count'):
                matrix._validate(self.req, self.config)

    def test_launch_requires_hard_preflight_before_freezing(self):
        with patch.object(matrix, '_preview', return_value={'ready': False, 'cells': [], 'estimated_input_bytes': 0}), \
             patch.object(opt, 'ensure_idle'), patch.object(matrix, 'freeze') as freeze:
            with self.assertRaises(HTTPException) as error:
                matrix.start(self.req, BackgroundTasks(), self.config)
        self.assertEqual(error.exception.status_code, 422)
        freeze.assert_not_called()

    def test_launch_freezes_each_pair_frame_with_separate_wallet(self):
        seen = []
        def fake_freeze(request, config):
            index = len(seen)
            pair = config['exchange']['pair_whitelist'][0]
            seen.append((pair, request.settings['timeframe'], request.settings['dry_run_wallet']))
            path = self.base / 'runs' / str(index)
            path.mkdir(parents=True)
            return path, {'input_bytes': 10, 'input_manifest_sha256': 'hash' + str(index),
                          'preflight_id': 'preflight' + str(index)}
        cells = [{'pair': p, 'timeframe': frame, 'dataset_sha256': f'data-{p}-{frame}'}
                 for p in self.req.pairs for frame in self.req.timeframes]
        preview = {'ready': True, 'cells': cells, 'estimated_input_bytes': 40}
        background = BackgroundTasks()
        with patch.object(matrix, '_preview', return_value=preview), \
             patch.object(opt, 'ensure_idle'), patch.object(matrix, 'freeze', side_effect=fake_freeze):
            result = matrix.start(self.req, background, self.config)
        self.assertEqual(result['status'], 'prepared')
        self.assertEqual(result['total_cells'], 4)
        self.assertEqual(len(background.tasks), 1)
        self.assertEqual(seen, [('BTC/USDT:USDT', '15m', 1000), ('BTC/USDT:USDT', '1h', 1000),
                                ('ETH/USDT:USDT', '15m', 1000), ('ETH/USDT:USDT', '1h', 1000)])
        self.assertEqual(len({str(matrix.root(self.config) / result['id'] / 'cells' / str(i)) for i in range(4)}), 4)
        for cell in result['cells']:
            self.assertEqual(cell['wallet_usdt'], 1000)
            self.assertEqual(cell['status'], 'pending')
        matrix._release(result['id'])

    def _record(self, status='running'):
        uid = 'a' * 32
        path = matrix.root(self.config) / uid
        path.mkdir(exist_ok=True)
        record = {'id': uid, 'strategy': 'Sample', 'status': status, 'cells': [],
                  'active_process_identity': {'pid': 123, 'start_ticks': '4'},
                  'active_command': ['python', '-m', 'freqtrade']}
        write_check(path / 'record.json', record)
        return path, record

    def test_restart_interrupts_without_signalling_foreign_pid(self):
        path, record = self._record()
        with patch.object(matrix, '_orphan_alive', return_value=True):
            latest = matrix.get_matrix(record['id'], self.config)
            self.assertEqual(latest['status'], 'interrupted')
            self.assertTrue(latest['orphan_process_alive'])
            with self.assertRaises(HTTPException):
                matrix.guard_matrix_orphans(self.config)
            with patch.object(opt, 'stop_owned_group') as stop:
                matrix.cancel(record['id'], BackgroundTasks(), self.config)
                stop.assert_not_called()
        with patch.object(matrix, '_orphan_alive', return_value=False):
            self.assertFalse(matrix.get_matrix(record['id'], self.config)['orphan_process_alive'])
        self.assertEqual(json.loads((path / 'record.json').read_text())['status'], 'interrupted')

    def test_cancel_only_signals_exact_owned_process(self):
        _, record = self._record()
        class Child:
            pid = 321
        child = Child()
        matrix._active_id = record['id']
        matrix._owned[record['id']] = child
        with patch.object(opt, 'stop_owned_group') as stop:
            answer = matrix.cancel(record['id'], BackgroundTasks(), self.config)
        self.assertEqual(answer['status'], 'cancelling')
        stop.assert_called_once_with(child, matrix.signal.SIGINT)


if __name__ == '__main__':
    unittest.main()
