import asyncio
import hashlib
import json
import tempfile
import sys
from types import ModuleType
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from fastapi import BackgroundTasks, HTTPException
from freqtrade.rpc.api_server.api_local_strategies import Create, create
from freqtrade.rpc.api_server.api_studio import Manifest, write_check
from freqtrade.rpc.api_server.api_runs import (freeze, finish, start_run, list_runs,
                                               verify_run, run_path, download_artifact,
                                               clear_local_imports, ImportArtifactRequest, import_artifact)


class FrozenRunChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        (base / 'strategies').mkdir()
        (base / 'data').mkdir()
        (base / 'data/BTC.feather').write_bytes(b'original frozen candle bytes')
        self.config = {'user_data_dir': base, 'datadir': base / 'data', 'dry_run': True,
                       'fee': 0.0005, 'exchange': {'name': 'binance', 'key': 'NEVER_COPY_ME',
                       'pair_whitelist': ['BTC/USDT:USDT']},
                       'api_server': {'password': 'NEVER_COPY_ME'}}
        self.doc = create(Create(name='FrozenSample'), self.config)
        self.req = Manifest(strategy='FrozenSample', revision=self.doc['revision'], settings={
            'timeframe': '15m', 'timeframe_detail': '1m', 'timerange': '20260918-20261022',
            'stake_amount': '100', 'dry_run_wallet': 1000, 'max_open_trades': 2,
            'enable_protections': False})

    def tearDown(self):
        self.tmp.cleanup()

    def make_snapshot(self):
        with patch('freqtrade.rpc.api_server.api_runs.manifest', return_value={'id': 'preflight'}):
            return freeze(self.req, self.config)

    def native_result(self, p, record, source=None):
        output = p / 'output/freqpilot-test.zip'
        with ZipFile(output, 'w') as archive:
            archive.writestr('freqpilot-test_FrozenSample.py', source or self.doc['content'])
            parameter=p/'inputs/strategies/FrozenSample.json'
            if parameter.exists():archive.write(parameter,'freqpilot-test_FrozenSample.json')
            archive.writestr('freqpilot-test.json', json.dumps({'strategy': {'FrozenSample': {
                'total_trades': 2, 'profit_total_abs': -1.25, 'profit_total': -0.00125}}}))
        output.with_suffix('.meta.json').write_text(json.dumps({'FrozenSample': {'run_id': 'native-id'}}))
        record['job_id'] = 'native-job'
        write_check(p / 'record.json', record)
        from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
        with patch.dict(ApiBG.jobs, {'native-job': {'status': 'success', 'error': None}}):
            finish(record['id'], self.config)

    def test_saved_inputs_are_independent_of_future_source_and_data(self):
        p, record = self.make_snapshot()
        (self.config['datadir'] / 'BTC.feather').write_bytes(b'updated candles')
        (self.config['user_data_dir'] / 'strategies/FrozenSample.py').write_text('# new source')
        self.native_result(p, record)
        saved = list_runs('FrozenSample', self.config)['runs'][0]
        self.assertEqual(saved['status'], 'success')
        self.assertEqual(saved['summary']['profit_total_abs'], -1.25)
        self.assertTrue(verify_run(record['id'], self.config)['valid'])
        with ZipFile(p / 'artifact.zip') as bundle:
            self.assertEqual(bundle.read('inputs/data/BTC.feather'), b'original frozen candle bytes')
            self.assertEqual(bundle.read('inputs/strategies/FrozenSample.py').decode(), self.doc['content'])
            self.assertNotIn(b'NEVER_COPY_ME', bundle.read('inputs/config.json'))
        self.assertTrue((self.config['user_data_dir'] / 'backtest_results/freqpilot-test.zip').exists())

    def test_changed_snapshot_or_native_source_cannot_be_presented_as_verified(self):
        for change_input in (False, True):
            with self.subTest(change_input=change_input):
                p, record = self.make_snapshot()
                if change_input:
                    (p / 'inputs/data/BTC.feather').write_bytes(b'changed after snapshot')
                self.native_result(p, record, source=None if change_input else '# wrong native strategy')
                saved = json.loads((p / 'record.json').read_text())
                self.assertEqual(saved['status'], 'failed')
                self.assertFalse((p / 'artifact.zip').exists())

    def test_tampered_package_and_path_escape_are_rejected(self):
        p, record = self.make_snapshot()
        self.native_result(p, record)
        with (p / 'artifact.zip').open('ab') as stream:
            stream.write(b'changed')
        self.assertFalse(verify_run(record['id'], self.config)['valid'])
        with self.assertRaises(HTTPException):
            download_artifact(record['id'], self.config)
        with self.assertRaises(HTTPException):
            run_path('../config.json', self.config)

    def test_launch_uses_frozen_paths_and_forces_native_cache_reset(self):
        from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
        received = {}
        async def native(settings, tasks, config):
            received.update(config)
            self.assertEqual(settings.backtest_cache, 'none')
            ApiBG.bt['job_id'] = 'delegated-job'
            return {'running': True}
        old_id = ApiBG.bt['job_id']
        try:
            with patch.object(ApiBG, 'analysis_running', False), \
                 patch('freqtrade.rpc.api_server.api_runs.manifest', return_value={'id': 'preflight'}), \
                 patch('freqtrade.rpc.api_server.api_backtest.api_delete_backtest') as reset, \
                 patch('freqtrade.rpc.api_server.api_backtest.api_start_backtest', side_effect=native):
                record = asyncio.run(start_run(self.req, BackgroundTasks(), self.config))
            reset.assert_called_once()
            self.assertEqual(record['status'], 'running')
            self.assertEqual(record['job_id'], 'delegated-job')
            self.assertNotEqual(received['datadir'], self.config['datadir'])
            self.assertEqual(received['datadir'].parent, received['user_data_dir'])
            self.assertEqual(Path(received['strategy_path']).parent, received['user_data_dir'])
            self.assertNotIn('NEVER_COPY_ME', json.dumps(received['original_config']))
        finally:
            ApiBG.bt['job_id'] = old_id

    def test_cached_local_helper_is_removed_but_engine_import_is_retained(self):
        helper = ModuleType('freqpilot_test_helper')
        helper.__file__ = str(self.config['user_data_dir'] / 'strategies/helper.py')
        with patch.dict(sys.modules, {'freqpilot_test_helper': helper}):
            clear_local_imports(self.config)
            self.assertNotIn('freqpilot_test_helper', sys.modules)
            self.assertTrue('freqtrade.rpc.api_server.api_runs' in sys.modules)


    def test_import_artifact_restores_verified_bundle_into_clean_workspace_without_touching_library(self):
        import base64
        from freqtrade.rpc.api_server.api_replay import replay_preview
        self.config.update(trading_mode='futures', margin_mode='isolated', stake_currency='USDT',
                           pairlists=[{'method': 'StaticPairList'}], stoploss=-0.02)
        p, record = self.make_snapshot()
        self.native_result(p, record)
        saved = json.loads((p / 'record.json').read_text())
        raw_zip = (p / 'artifact.zip').read_bytes()
        b64 = base64.b64encode(raw_zip).decode('ascii')

        with tempfile.TemporaryDirectory() as clean_tmp:
            clean_base = Path(clean_tmp)
            (clean_base / 'strategies').mkdir()
            (clean_base / 'data').mkdir()
            clean_cfg = {**self.config, 'user_data_dir': clean_base, 'datadir': clean_base / 'data'}

            # Wrong expected SHA256 must be rejected before writing anything
            with self.assertRaises(HTTPException):
                import_artifact(ImportArtifactRequest(archive_base64=b64, expected_sha256='0' * 64), clean_cfg)
            self.assertFalse((clean_base / 'freqpilot/runs' / saved['id']).exists())

            # Valid import succeeds, verifies, populates backtest_results, and can be replayed without overwriting library strategies
            imported = import_artifact(
                ImportArtifactRequest(archive_base64=b64, expected_sha256=saved['artifact_sha256']),
                clean_cfg,
            )
            self.assertEqual(imported['id'], saved['id'])
            self.assertEqual(imported['artifact_sha256'], saved['artifact_sha256'])
            self.assertTrue(verify_run(saved['id'], clean_cfg)['valid'])
            self.assertTrue((clean_base / 'backtest_results/freqpilot-test.zip').is_file())
            self.assertFalse((clean_base / 'strategies/FrozenSample.py').exists())
            preview = replay_preview(saved['id'], clean_cfg)
            self.assertEqual(preview['strategy'], 'FrozenSample')
            self.assertEqual(preview['artifact_sha256'], saved['artifact_sha256'])

            # Tampered member bytes inside zip must be rejected
            with ZipFile(p / 'artifact.zip') as zf:
                entries = [(i, zf.read(i)) for i in zf.infolist()]
            from io import BytesIO
            tampered_buf = BytesIO()
            with ZipFile(tampered_buf, 'w') as zf:
                for info, data in entries:
                    zf.writestr(info, b'corrupted' if info.filename == 'inputs/data/BTC.feather' else data)
            tampered_b64 = base64.b64encode(tampered_buf.getvalue()).decode('ascii')
            with tempfile.TemporaryDirectory() as clean_tmp2:
                clean_base2 = Path(clean_tmp2)
                (clean_base2 / 'strategies').mkdir()
                (clean_base2 / 'data').mkdir()
                clean_cfg2 = {**self.config, 'user_data_dir': clean_base2, 'datadir': clean_base2 / 'data'}
                with self.assertRaises(HTTPException):
                    import_artifact(ImportArtifactRequest(archive_base64=tampered_b64), clean_cfg2)

if __name__ == '__main__':
    unittest.main()
