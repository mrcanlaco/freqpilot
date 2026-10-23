"""Offline boundaries for bounded native sensitivity jobs."""
import importlib.util
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from fastapi import HTTPException

spec = importlib.util.spec_from_file_location('sensitivity_under_test', Path(__file__).with_name('api_sensitivity.py'))
sense = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sense)


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.library = self.base / 'strategies'
        self.library.mkdir()
        self.source = self.library / 'Sample.py'
        self.source.write_text('class Sample: pass')
        self.revision = hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.config = {'dry_run': True, 'user_data_dir': self.base, 'datadir': self.base / 'data',
                       'fee': .0005, 'dry_run_wallet': 1000, 'stake_amount': 100,
                       'max_open_trades': 2, 'exchange': {'name': 'binance',
                       'pair_whitelist': ['BTC/USDT:USDT']}}
        (self.base / 'data').mkdir()
        self.schema = {'strategy': 'Sample', 'revision': self.revision,
                       'parameter_revision': 'none', 'schema_revision': 's' * 64,
                       'fields': [
                           {'name': 'buy_level', 'space': 'buy', 'param_type': 'IntParameter',
                            'value': 10, 'load': True, 'optimize': True, 'low': 1, 'high': 20},
                           {'name': 'sell_level', 'space': 'sell', 'param_type': 'DecimalParameter',
                            'value': .5, 'load': True, 'optimize': True, 'low': .1, 'high': .9,
                            'decimals': 2}]}
        self.req = sense.SensitivityRequest(strategy='Sample', revision=self.revision,
            settings={'timerange': '20260918-20261022', 'timeframe': '15m',
                      'timeframe_detail': '1m', 'dry_run_wallet': 1000,
                      'stake_amount': '100', 'max_open_trades': 2,
                      'enable_protections': False},
            axes=[{'name': 'buy_level', 'step': 2, 'radius': 1},
                  {'name': 'sell_level', 'step': .1, 'radius': 1}],
            fee_scenarios=[.0005, .001])
        self.schema_patch = patch.object(sense, 'inspect_parameters', return_value=self.schema)
        self.library_patch = patch.object(sense, 'strategy_root', return_value=self.library)
        self.schema_patch.start(); self.library_patch.start()

    def tearDown(self):
        self.library_patch.stop(); self.schema_patch.stop()
        self.temp.cleanup()

    def test_preview_exact_grid_fees_baseline_and_unrun_null(self):
        planned = sense.preview(self.req, self.config)
        self.assertEqual(planned['estimated_backtests'], 18)
        self.assertEqual(planned['axes'][0]['values'], [8, 10, 12])
        self.assertEqual(planned['axes'][1]['values'], [.4, .5, .6])
        self.assertEqual({cell['fee'] for cell in planned['cells']}, {.0005, .001})
        self.assertTrue(all(cell['result'] is None and cell['status'] == 'pending' for cell in planned['cells']))
        self.assertNotIn('_source_hashes', planned)

    def test_invalid_grid_and_fee_do_not_invent_cells(self):
        req = self.req.model_copy(deep=True)
        req.axes[0].radius = 2
        req.axes[1].radius = 2
        with self.assertRaises(HTTPException): sense.plan(req, self.config)  # 5x5x2 > 30
        req = self.req.model_copy(deep=True)
        req.fee_scenarios = [.001]
        with self.assertRaises(HTTPException): sense.plan(req, self.config)
        req = self.req.model_copy(deep=True)
        req.axes[1].step = .001
        with self.assertRaises(HTTPException): sense.plan(req, self.config)

    def test_preview_rejects_unknown_settings_before_snapshot(self):
        req = self.req.model_copy(deep=True)
        req.settings['fee'] = 0
        with self.assertRaises(HTTPException) as raised:
            sense.preview(req, self.config)
        self.assertEqual(raised.exception.status_code, 422)

    def test_cancel_never_signals_unowned_or_restarted_child(self):
        job = self.base / 'freqpilot/sensitivity' / uuid4().hex
        job.mkdir(parents=True)
        (job / 'record.json').write_text(json.dumps({
            'id': job.name, 'status': 'running', 'strategy': 'Sample',
            'cells': [{'index': 0, 'status': 'running', 'result': None}],
            'active_process_identity': None, 'active_command': None}))
        with patch.object(sense, 'root', return_value=job.parent), \
             patch.object(sense, 'stop_owned_group') as stop:
            result = sense.cancel(job.name, object(), self.config)
            self.assertEqual(result['status'], 'interrupted')
            stop.assert_not_called()

    def test_parameter_values_are_native_validated_and_never_edit_live_json(self):
        original = self.library / 'Sample.json'
        original.write_text(json.dumps({'strategy_name': 'Sample', 'ft_stratparam_v': 1,
                                        'params': {'stoploss': {'stoploss': -.03}}}))
        cell_dir = self.base / 'job/cells/0/inputs/strategies'
        cell_dir.mkdir(parents=True)
        dest = cell_dir / 'Sample.json'
        dest.write_bytes(original.read_bytes())
        record = {'strategy': 'Sample', 'schema': self.schema,
                  'baseline': {'buy_level': 10, 'sell_level': .5}}
        cell = {'index': 0, 'parameters': {'buy_level': 12, 'sell_level': .6}}
        before = hashlib.sha256(original.read_bytes()).hexdigest()
        value = sense._parameter_file(self.base / 'job', record, cell)
        params = json.loads(dest.read_text())['params']
        self.assertEqual(params['buy']['buy_level'], 12)
        self.assertEqual(params['sell']['sell_level'], .6)
        self.assertEqual(params['stoploss']['stoploss'], -.03)
        self.assertEqual(value, hashlib.sha256(dest.read_bytes()).hexdigest())
        self.assertEqual(before, hashlib.sha256(original.read_bytes()).hexdigest())

    def test_runtime_fee_isolated_from_frozen_config_and_data(self):
        job = self.base / 'job'
        (job / 'cells/0').mkdir(parents=True)
        frozen = {'config': {'fee': .0005, 'dry_run': True, 'exchange': {'name': 'binance'},
                             'strategy': 'Sample', 'stake_amount': '100',
                             'dry_run_wallet': 1000, 'max_open_trades': 2}}
        file = sense._runtime(job, {'index': 0, 'fee': .001}, frozen)
        runtime = json.loads(file.read_text())
        self.assertEqual(runtime['fee'], .001)
        self.assertEqual(frozen['config']['fee'], .0005)
        self.assertEqual(runtime['datadir'], str(job / 'inputs/data'))
        self.assertTrue(runtime['dry_run'])
        self.assertEqual(runtime['stake_amount'], 100.0)

    def test_summary_accepts_only_native_zip_with_matching_code_params_and_runtime(self):
        job = self.base / 'job'
        target = job / 'cells/0'
        (target / 'output').mkdir(parents=True)
        (target / 'inputs/strategies').mkdir(parents=True)
        params = target / 'inputs/strategies/Sample.json'
        params.write_text('{"strategy_name":"Sample","ft_stratparam_v":1,"params":{}}')
        runtime = target / 'runtime.json'
        runtime.write_text('{"fee":0.0005}')
        name = 'native-sensitivity'
        archive = target / 'output' / (name + '.zip')
        with ZipFile(archive, 'w') as bundle:
            bundle.writestr(name + '_Sample.py', self.source.read_bytes())
            bundle.writestr(name + '_Sample.json', params.read_bytes())
            bundle.writestr(name + '.json', json.dumps({'strategy': {'Sample': {'total_trades': 1,
                                 'profit_total_abs': 1.2, 'backtest_start': '2026-09-18',
                                 'backtest_end': '2026-10-21'}}}))
        record = {'strategy': 'Sample', 'revision': self.revision}
        result = sense._summary(job, {'index': 0}, record, sense.digest(params), sense.digest(runtime))
        self.assertEqual(result['summary']['total_trades'], 1)
        self.assertEqual(result['artifact_sha256'], sense.digest(archive))
        runtime.write_text('{"fee":0.001}')
        with self.assertRaises(ValueError):
            sense._summary(job, {'index': 0}, record, sense.digest(params), result['runtime_sha256'])

    def test_interrupted_record_keeps_completed_cells_and_does_not_resume(self):
        job = self.base / 'sensitivity' / uuid4().hex
        job.mkdir(parents=True)
        record = {'id': job.name, 'status': 'running', 'strategy': 'Sample',
                  'cells': [{'index': 0, 'status': 'success', 'result': {'summary': {'total_trades': 3}}},
                            {'index': 1, 'status': 'pending', 'result': None}],
                  'active_process_identity': None, 'active_command': None}
        (job / 'record.json').write_text(json.dumps(record))
        old = sense._active_id
        sense._active_id = None
        try: refreshed = sense._refreshed(job)
        finally: sense._active_id = old
        self.assertEqual(refreshed['status'], 'interrupted')
        self.assertEqual(refreshed['cells'][0]['status'], 'success')
        self.assertIsNone(refreshed['cells'][1]['result'])
        self.assertFalse(refreshed['orphan_process_alive'])


if __name__ == '__main__': unittest.main()
