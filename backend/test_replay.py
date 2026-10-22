import asyncio
import hashlib
import json
import stat
import unittest
from copy import deepcopy
from unittest.mock import patch
from zipfile import ZipFile, ZipInfo

from fastapi import BackgroundTasks, HTTPException
from freqtrade.rpc.api_server.api_runs import digest, finish, list_runs, run_path, verify_run
from freqtrade.rpc.api_server.api_replay import ReplayRequest, replay_preview, replay_run, compare_replay, native_stats
from freqtrade.rpc.api_server.api_studio import write_check
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG
import test_runs


class ReplayChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = test_runs.FrozenRunChecks()
        self.fixture.setUp()
        self.config = self.fixture.config
        self.config.update(trading_mode='futures', margin_mode='isolated', stake_currency='USDT',
                           pairlists=[{'method': 'StaticPairList'}], stoploss=-0.02)
        self.p, self.record = self.fixture.make_snapshot()
        self.complete(self.p, self.record)
        self.record = json.loads((self.p/'record.json').read_text())

    def tearDown(self): self.fixture.tearDown()

    def complete(self, p, record, profit=-1.25, order_cost=100):
        name = 'replay-test-'+record['id']
        stats = {'total_trades': 1, 'profit_total_abs': profit, 'profit_total': profit/1000,
                 'max_drawdown_account': 0.002, 'starting_balance': 1000, 'final_balance': 1000+profit,
                 'backtest_start': '2026-09-18', 'backtest_end': '2026-10-22', 'timeframe': '15m',
                 'trades': [{'pair': 'BTC/USDT:USDT', 'profit_abs': profit, 'funding_fees': -0.1,
                             'orders': [{'cost': order_cost, 'ft_is_entry': True}]}]}
        with ZipFile(p/'output'/f'{name}.zip', 'w') as z:
            z.write(p/'inputs/strategies/FrozenSample.py', f'{name}_FrozenSample.py')
            if (p/'inputs/strategies/FrozenSample.json').exists():
                z.write(p/'inputs/strategies/FrozenSample.json', f'{name}_FrozenSample.json')
            z.writestr(name+'.json', json.dumps({'strategy': {'FrozenSample': stats}}))
        (p/'output'/f'{name}.meta.json').write_text(json.dumps({'FrozenSample': {'run_id': record['id']}}))
        record['job_id'] = record['id']
        write_check(p/'record.json', record)
        with patch.dict(ApiBG.jobs, {record['id']: {'status': 'success', 'error': None}}):
            finish(record['id'], self.config)

    def start(self, captured=None):
        async def native(settings, tasks, cfg):
            if captured is not None: captured.update(deepcopy(cfg))
            self.assertEqual(settings.backtest_cache, 'none')
            ApiBG.bt['job_id'] = 'new-replay-job'
        old = ApiBG.bt['job_id']
        try:
            with patch.object(ApiBG, 'analysis_running', False), \
                 patch('freqtrade.rpc.api_server.api_backtest.api_delete_backtest') as reset, \
                 patch('freqtrade.rpc.api_server.api_backtest.api_start_backtest', side_effect=native):
                result = asyncio.run(replay_run(self.record['id'], ReplayRequest(artifact_sha256=self.record['artifact_sha256']), BackgroundTasks(), self.config))
                reset.assert_called_once()
                return result
        finally: ApiBG.bt['job_id'] = old

    def test_preview_and_launch_use_archive_after_live_and_snapshot_files_change(self):
        before = digest(self.p/'artifact.zip')
        (self.p/'inputs/data/BTC.feather').write_bytes(b'tampered loose snapshot')
        (self.config['datadir']/'BTC.feather').write_bytes(b'new live prices')
        (self.config['user_data_dir']/'strategies/FrozenSample.py').unlink()
        self.config.update(fee=0.9, stoploss=-0.9, minimal_roi={'0': 5}, freqai={'enabled': True})
        self.config['exchange']['pair_whitelist'] = ['ETH/USDT:USDT']
        preview = replay_preview(self.record['id'], self.config)
        self.assertEqual(preview['fee'], 0.0005)
        self.assertEqual(preview['pairs'], ['BTC/USDT:USDT'])
        received = {}
        result = self.start(received)
        new = run_path(result['id'], self.config)
        self.assertNotEqual(result['id'], self.record['id'])
        self.assertEqual((new/'inputs/data/BTC.feather').read_bytes(), b'original frozen candle bytes')
        self.assertEqual((new/'inputs/strategies/FrozenSample.py').read_text(), self.fixture.doc['content'])
        self.assertEqual(received['fee'], 0.0005)
        self.assertEqual(received['stoploss'], -0.02)
        self.assertEqual(received['exchange']['pair_whitelist'], ['BTC/USDT:USDT'])
        self.assertNotIn('minimal_roi', received)
        self.assertNotIn('freqai', received)
        self.assertNotIn('api_server', received)
        self.assertNotIn('NEVER_COPY_ME', json.dumps(received, default=str))
        self.assertEqual(digest(self.p/'artifact.zip'), before)
        self.assertFalse((self.config['user_data_dir']/'strategies/FrozenSample.py').exists())

    def test_stale_or_corrupt_package_and_busy_engine_never_launch(self):
        with patch('freqtrade.rpc.api_server.api_backtest.api_start_backtest') as launch:
            for busy, sha in [(True, self.record['artifact_sha256']), (False, '0'*64)]:
                with self.subTest(busy=busy), patch.object(ApiBG, 'analysis_running', busy), self.assertRaises(HTTPException):
                    asyncio.run(replay_run(self.record['id'], ReplayRequest(artifact_sha256=sha), BackgroundTasks(), self.config))
            with (self.p/'artifact.zip').open('ab') as stream: stream.write(b'changed')
            with self.assertRaises(HTTPException): replay_preview(self.record['id'], self.config)
            launch.assert_not_called()

    def test_archived_parameter_bytes_survive_new_live_defaults(self):
        parameter = self.config['user_data_dir']/'strategies/FrozenSample.json'
        original_bytes = b'{"strategy_name":"FrozenSample","params":{"buy":{"buy_length":17}}}'
        parameter.write_bytes(original_bytes)
        self.p, record = self.fixture.make_snapshot()
        self.complete(self.p, record)
        self.record = json.loads((self.p/'record.json').read_text())
        parameter.write_text('{"params":{"buy":{"buy_length":99}}}')
        replay = self.start()
        self.assertEqual((run_path(replay['id'], self.config)/'inputs/strategies/FrozenSample.json').read_bytes(), original_bytes)
        self.assertIn('99', parameter.read_text())

    def corrupt_manifest(self, name, content=b'injected', symlink=False):
        frozen = json.loads((self.p/'inputs.json').read_text())
        frozen['files'][name] = hashlib.sha256(content).hexdigest()
        data = json.dumps(frozen).encode()
        with ZipFile(self.p/'artifact.zip') as z: entries = [(i, z.read(i)) for i in z.infolist() if i.filename != 'inputs.json']
        with ZipFile(self.p/'artifact.zip', 'w') as z:
            for info, value in entries: z.writestr(info, value)
            z.writestr('inputs.json', data)
            info = ZipInfo(name)
            if symlink: info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, content)
        (self.p/'inputs.json').write_bytes(data)
        self.record.update(input_manifest_sha256=digest(self.p/'inputs.json'), artifact_sha256=digest(self.p/'artifact.zip'))
        write_check(self.p/'record.json', self.record)

    def test_path_escape_in_self_consistent_package_is_rejected(self):
        self.corrupt_manifest('inputs/strategies/../../escaped.py')
        with self.assertRaises(HTTPException): replay_preview(self.record['id'], self.config)
        self.assertFalse((self.config['user_data_dir']/'escaped.py').exists())

    def test_symlink_member_in_self_consistent_package_is_rejected(self):
        self.corrupt_manifest('inputs/strategies/helper.py', b'../../config.json', symlink=True)
        with self.assertRaises(HTTPException): replay_preview(self.record['id'], self.config)

    def test_corrupt_member_inside_otherwise_verified_archive_is_rejected(self):
        with ZipFile(self.p/'artifact.zip') as z: entries = [(i, z.read(i)) for i in z.infolist()]
        with ZipFile(self.p/'artifact.zip', 'w') as z:
            for info, value in entries:
                z.writestr(info, b'wrong bytes' if info.filename == 'inputs/data/BTC.feather' else value)
        self.record['artifact_sha256'] = digest(self.p/'artifact.zip')
        write_check(self.p/'record.json', self.record)
        self.assertTrue(verify_run(self.record['id'], self.config)['valid'])
        with self.assertRaises(HTTPException): replay_preview(self.record['id'], self.config)

    def test_completed_replay_retains_new_package_and_compares_all_order_fields(self):
        replay = self.start()
        new = run_path(replay['id'], self.config)
        self.complete(new, replay)
        saved = json.loads((new/'record.json').read_text())
        self.assertEqual(saved['status'], 'success')
        self.assertEqual(saved['replay_comparison']['status'], 'matched')
        self.assertTrue(verify_run(saved['id'], self.config)['valid'])
        replay2 = self.start()
        newer = run_path(replay2['id'], self.config)
        self.complete(newer, replay2, order_cost=100.000001)
        saved2 = json.loads((newer/'record.json').read_text())
        self.assertEqual(saved2['replay_comparison']['status'], 'different')
        self.assertEqual(saved2['replay_comparison']['different_trades'], 1)
        self.assertEqual(saved2['replay_comparison']['different_metrics'], [])

    def test_parent_corruption_does_not_erase_completed_new_result(self):
        replay = self.start()
        with (self.p/'artifact.zip').open('ab') as stream: stream.write(b'changed')
        new = run_path(replay['id'], self.config)
        self.complete(new, replay)
        saved = json.loads((new/'record.json').read_text())
        self.assertEqual(saved['status'], 'success')
        self.assertEqual(saved['replay_comparison']['status'], 'unavailable')
        self.assertTrue(verify_run(saved['id'], self.config)['valid'])

    def test_nonfinite_trade_field_is_not_normalized_into_a_matching_null(self):
        replay = self.start()
        stats = native_stats(self.p, self.record)
        stats['trades'][0]['profit_abs'] = float('nan')
        with patch('freqtrade.rpc.api_server.api_replay.native_stats', return_value=stats):
            self.assertEqual(compare_replay(replay, self.config)['status'], 'unavailable')


if __name__ == '__main__': unittest.main()
