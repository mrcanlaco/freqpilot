"""Offline tests for evidence capture and conservative trade matching."""
import importlib.util
import asyncio
import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import BackgroundTasks, HTTPException
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG

spec = importlib.util.spec_from_file_location('paper_reconcile_under_test', Path(__file__).with_name('api_paper_reconcile.py'))
reconcile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reconcile)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.profile_id = uuid4().hex
        self.folder = self.base / 'paper/profiles' / self.profile_id
        self.folder.mkdir(parents=True)
        self.start = datetime(2026, 10, 20, 8, tzinfo=timezone.utc)
        self.end = self.start + timedelta(hours=3)
        self.settings = {'pairs': ['BTC/USDT:USDT'], 'timeframe': '5m',
                         'wallet': 1000, 'stake': 100, 'max_open_trades': 2, 'fee': .0005}
        self.profile = {'id': self.profile_id, 'wrapper': 'FPPaper_' + self.profile_id[:16],
                        'strategy': 'Sample', 'revision': 'a' * 64, 'run_id': uuid4().hex,
                        'config_sha256': 'b' * 64, 'source_hashes': {'strategies/Sample.py': 'a' * 64,
                                                                      'strategies/Sample.json': 'c' * 64},
                        'settings': self.settings, 'engine': '2026.9', 'label': 'Paper sample'}
        self.cfg = {'db_url': 'sqlite:///' + str(self.folder / 'paper.sqlite')}
        self.config = {'dry_run': True}
        self.root_patch = patch.object(reconcile, 'paper_root', return_value=self.base / 'paper')
        self.profile_patch = patch.object(reconcile, 'verify_profile', return_value=(self.cfg, self.profile))
        self.native_patch = patch.object(reconcile, '_native_view', return_value={
            'online': True, 'state': 'running', 'profile_matches': True, 'configuration_marker': 'same'})
        self.root_patch.start(); self.profile_patch.start(); self.native_patch.start()

    def tearDown(self):
        self.native_patch.stop(); self.profile_patch.stop(); self.root_patch.stop()
        self.temp.cleanup()

    def db(self):
        conn = sqlite3.connect(self.folder / 'paper.sqlite')
        conn.execute('CREATE TABLE trades (' + ','.join(
            field + (' INTEGER' if field in ('id', 'is_open', 'is_short') else ' TEXT')
            for field in reconcile._TRADE_FIELDS) + ')')
        conn.execute('CREATE TABLE orders (' + ','.join(
            field + (' INTEGER' if field in ('id', 'ft_trade_id') else ' TEXT')
            for field in reconcile._ORDER_FIELDS) + ')')
        return conn

    def add_trade(self, conn, uid=1, opened=None, closed=None, short=False, is_open=False):
        row = {'id': uid, 'pair': 'BTC/USDT:USDT', 'is_short': int(short), 'is_open': int(is_open),
               'open_date': (opened or self.start + timedelta(minutes=5)).isoformat(),
               'close_date': closed.isoformat() if closed else None, 'open_rate': 50000,
               'close_rate': 49900, 'stake_amount': 100, 'amount': .002,
               'fee_open': .0005, 'fee_close': .0005, 'funding_fees': -.01,
               'close_profit': .004, 'close_profit_abs': .4, 'exit_reason': 'roi',
               'enter_tag': 'signal', 'strategy': self.profile['wrapper']}
        conn.execute('INSERT INTO trades (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')',
                     list(row.values()))

    def add_order(self, conn, uid, side, amount, price, filled_at):
        row = {'id': uid, 'ft_trade_id': 1, 'ft_order_side': side, 'status': 'closed',
               'filled': amount, 'average': price, 'order_filled_date': filled_at.isoformat()}
        conn.execute('INSERT INTO orders (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')',
                     list(row.values()))

    def session(self):
        return {'id': uuid4().hex, 'profile_id': self.profile_id, 'strategy': 'Sample',
                'revision': 'a' * 64, 'engine': '2026.9', 'source_run_id': self.profile['run_id'],
                'profile_config_sha256': 'b' * 64, 'source_hashes': self.profile['source_hashes'],
                'settings': self.settings, 'label': 'sample', 'status': 'closed',
                'started_at': self.start.isoformat(), 'closed_at': self.end.isoformat(),
                'observations': [{'native': {'configuration_marker': 'same'}, 'database_available': True,
                                  'truncated': False}], 'gaps': [], 'paper_trades': [], 'comparisons': []}

    def native_trade(self, opened=None, closed=None):
        return {'pair': 'BTC/USDT:USDT', 'is_short': False,
                'open_date': (opened or self.start + timedelta(minutes=5)).isoformat(),
                'close_date': (closed or self.start + timedelta(minutes=30)).isoformat(),
                'open_rate': 50000, 'close_rate': 49900, 'stake_amount': 100,
                'max_stake_amount': 100, 'amount': .002, 'leverage': 1,
                'fee_open': .0005, 'fee_close': .0005,
                'funding_fees': -.01, 'profit_ratio': .004, 'profit_abs': .4,
                'exit_reason': 'roi', 'enter_tag': 'signal',
                'orders': [{'ft_is_entry': True, 'amount': .002, 'safe_price': 50000, 'cost': 100,
                            'order_filled_timestamp': (self.start + timedelta(minutes=5)).timestamp()*1000}]}

    def run_record(self):
        return {'id': uuid4().hex, 'strategy': 'Sample', 'revision': 'a' * 64,
                'engine': '2026.9', 'artifact_sha256': 'd' * 64,
                'settings': {'timerange': f'{int(self.start.timestamp())}-{int(self.end.timestamp())}'}}

    def frozen(self):
        return {'files': {'inputs/strategies/Sample.py': 'a' * 64,
                          'inputs/strategies/Sample.json': 'c' * 64},
                'config': {'dry_run': True, 'trading_mode': 'futures', 'margin_mode': 'isolated',
                           'exchange': {'name': 'binance', 'pair_whitelist': self.settings['pairs']},
                           'timeframe': '5m', 'dry_run_wallet': 1000, 'stake_amount': 100,
                           'max_open_trades': 2, 'fee': .0005}}

    def test_native_database_snapshot_includes_order_rows_and_flags_boundary_positions(self):
        with closing(self.db()) as conn, conn:
            self.add_trade(conn, opened=self.start-timedelta(minutes=5), closed=self.start+timedelta(minutes=30))
            self.add_order(conn, 1, 'buy', .001, 50000, self.start+timedelta(minutes=5))
            self.add_order(conn, 2, 'buy', .001, 50100, self.start+timedelta(minutes=10))
            self.add_order(conn, 3, 'sell', .001, 49900, self.start+timedelta(minutes=20))
            self.add_order(conn, 4, 'sell', .001, 49950, self.start+timedelta(minutes=30))
        view = reconcile._db_view(self.cfg, self.folder, self.start, self.end)
        self.assertTrue(view['available'])
        self.assertEqual(len(view['trades']), 1)
        self.assertTrue(view['trades'][0]['predates_session'])
        self.assertEqual(len(view['trades'][0]['orders']), 4)
        with closing(sqlite3.connect(self.folder/'paper.sqlite')) as conn:
            self.assertEqual(conn.execute('SELECT count(*) FROM trades').fetchone()[0], 1)

    def test_session_does_not_backdate_and_records_missing_worker_as_gap(self):
        with closing(self.db()): pass
        with patch.object(reconcile, '_now', side_effect=[self.start.isoformat(), self.start.isoformat(), self.end.isoformat()]):
            observed = reconcile.start_session(reconcile.StartSession(profile_id=self.profile_id), self.config)
            self.assertEqual(observed['started_at'], self.start.isoformat())
            with patch.object(reconcile, '_native_view', return_value={'online': False, 'state': 'unavailable',
                          'profile_matches': False, 'configuration_marker': None}):
                closed = reconcile.close_session(observed['id'], self.config)
        self.assertEqual(closed['status'], 'closed')
        self.assertEqual(closed['closed_at'], self.end.isoformat())
        self.assertEqual(len(closed['gaps']), 1)
        self.assertEqual(reconcile.list_sessions(self.profile_id, self.config)['sessions'][0]['trade_count'], 0)
        self.assertEqual(reconcile.get_session(observed['id'], self.config)['evidence']['signals'], 'unobserved')

    def test_reject_inactive_profile_without_creating_session(self):
        with patch.object(reconcile, '_native_view', return_value={'online': True, 'state': 'running',
                          'profile_matches': False, 'configuration_marker': 'other'}):
            with self.assertRaises(HTTPException):
                reconcile.start_session(reconcile.StartSession(profile_id=self.profile_id), self.config)
        self.assertEqual(list((self.base/'paper/reconcile/sessions').glob('*.json')), [])

    def test_protocol_blocks_different_parameters_and_uncovered_time(self):
        session = self.session()
        frozen, run = self.frozen(), self.run_record()
        self.assertEqual(reconcile._protocol_issues(session, frozen, run), [])
        frozen['files']['inputs/strategies/Sample.json'] = 'changed'
        run['settings']['timerange'] = f'{int((self.start+timedelta(minutes=1)).timestamp())}-{int(self.end.timestamp())}'
        issues = reconcile._protocol_issues(session, frozen, run)
        self.assertTrue(any('tham số' in x for x in issues))
        self.assertTrue(any('bao phủ' in x for x in issues))

    def test_dca_partial_and_price_fee_funding_differences_are_reported(self):
        paper = {'id': 1, 'pair': 'BTC/USDT:USDT', 'is_short': False,
                 'open_date': (self.start+timedelta(minutes=5)).isoformat(),
                 'close_date': (self.start+timedelta(minutes=30)).isoformat(),
                 'open_rate': 50010, 'close_rate': 49900, 'stake_amount': 100,
                 'amount': .002, 'fee_open': .0006, 'fee_close': .0005,
                 'funding_fees': -.02, 'close_profit': .004, 'close_profit_abs': .4,
                 'exit_reason': 'roi', 'enter_tag': 'signal', 'orders': []}
        for i, side in enumerate(('buy', 'buy', 'sell', 'sell')):
            paper['orders'].append({'id': i, 'ft_order_side': side, 'filled': .001,
                                    'average': 50000+i, 'order_filled_date': (self.start+timedelta(minutes=5+i)).isoformat()})
        native = self.native_trade()
        result = reconcile._compare_trade(paper, native, 0)
        self.assertEqual(result['status'], 'different')
        self.assertEqual(result['structure']['paper_entry_orders'], 2)
        self.assertEqual(result['structure']['paper_exit_orders'], 2)
        fields = {f['field']: f for f in result['field_differences']}
        self.assertEqual(fields['open_rate']['delta_bps'], 2.0)
        self.assertIn('fee_open', fields)
        self.assertIn('funding_fees', fields)
        self.assertIn('order_count', fields)

    def test_ambiguous_matching_never_chooses_nearest_trade(self):
        session = self.session()
        p = {'id': 1, 'pair': 'BTC/USDT:USDT', 'is_short': False,
             'open_date': (self.start+timedelta(minutes=5)).isoformat(),
             'close_date': (self.start+timedelta(minutes=30)).isoformat(), 'is_open': False}
        session['paper_trades'] = [p]
        two = [self.native_trade(opened=self.start+timedelta(minutes=4)),
               self.native_trade(opened=self.start+timedelta(minutes=6))]
        rows = reconcile._compare_rows(session, two, '5m')
        self.assertEqual(rows[0]['status'], 'insufficient')
        self.assertNotIn('backtest_index', rows[0])

    def test_empty_paper_session_does_not_claim_match(self):
        session = self.session()
        path = reconcile._sessions_root(self.config)/(session['id']+'.json')
        path.write_text(json.dumps(session))
        run = self.run_record()
        with patch.object(reconcile, '_native_result', return_value=(self.frozen(), run, {'trades': [self.native_trade()]})):
            result = reconcile.compare_session(session['id'], reconcile.CompareRequest(run_id=run['id']), self.config)
        self.assertEqual(result['status'], 'insufficient')
        self.assertTrue(any('chưa có giao dịch' in x for x in result['warnings']))

    def test_closed_session_comparison_matches_exact_fields_then_flags_fee_change(self):
        session = self.session()
        native = self.native_trade()
        session['paper_trades'] = [{
            'id': 1, 'pair': native['pair'], 'is_short': False, 'is_open': False,
            'open_date': native['open_date'], 'close_date': native['close_date'],
            'open_rate': native['open_rate'], 'close_rate': native['close_rate'],
            'stake_amount': native['stake_amount'], 'max_stake_amount': native['max_stake_amount'],
            'amount': native['amount'], 'leverage': 1,
            'fee_open': native['fee_open'], 'fee_close': native['fee_close'],
            'funding_fees': native['funding_fees'], 'close_profit': native['profit_ratio'],
            'close_profit_abs': native['profit_abs'], 'exit_reason': native['exit_reason'],
            'enter_tag': native['enter_tag'], 'predates_session': False, 'continues_after_session': False,
            'orders': [{'id': 1, 'ft_order_side': 'buy', 'filled': .002, 'average': 50000, 'cost': 100,
                        'order_filled_date': native['open_date']}] }]
        run = self.run_record()
        stats = {'total_trades': 1, 'backtest_start': self.start.isoformat(),
                 'backtest_end': self.end.isoformat(), 'trades': [native]}
        path = reconcile._sessions_root(self.config)/(session['id']+'.json')
        path.write_text(json.dumps(session))
        with patch.object(reconcile, '_native_result', return_value=(self.frozen(), run, stats)):
            first = reconcile.compare_session(session['id'], reconcile.CompareRequest(run_id=run['id']), self.config)
            self.assertEqual(first['status'], 'matched')
            self.assertEqual(first['counts']['matched'], 1)
            session['paper_trades'][0]['fee_open'] = .0007
            path.write_text(json.dumps(session))
            second = reconcile.compare_session(session['id'], reconcile.CompareRequest(run_id=run['id']), self.config)
        self.assertEqual(second['status'], 'different')
        self.assertEqual(second['counts']['different'], 1)
        self.assertTrue(any(f['field'] == 'fee_open' for f in second['trades'][0]['field_differences']))

    def test_closed_session_launches_native_snapshot_only_for_matching_source(self):
        session = self.session()
        library = self.base / 'library'
        library.mkdir()
        source = library / 'Sample.py'
        source.write_text('class Sample: pass')
        params = library / 'Sample.json'
        params.write_text('{"strategy_name":"Sample"}')
        session['revision'] = self.profile['revision'] = hashlib.sha256(source.read_bytes()).hexdigest()
        session['source_hashes'] = self.profile['source_hashes'] = {
            'strategies/Sample.py': hashlib.sha256(source.read_bytes()).hexdigest(),
            'strategies/Sample.json': hashlib.sha256(params.read_bytes()).hexdigest()}
        path = reconcile._sessions_root(self.config) / (session['id'] + '.json')
        path.write_text(json.dumps(session))

        @contextmanager
        def origin(*args):
            yield None, {'config': {'exchange': {}}, 'settings': {'timeframe_detail': '1m'}}, None

        with patch.object(reconcile, 'strategy_root', return_value=library), \
             patch.object(reconcile, 'checked_bundle', side_effect=origin), \
             patch.object(reconcile, 'freeze') as freeze, \
             patch.object(reconcile, 'launch_snapshot') as launch, \
             patch.object(reconcile, 'reproducible_config', return_value={}), \
             patch.object(ApiBG, 'analysis_running', False):
            source.write_text('class Sample: changed')
            with self.assertRaises(HTTPException):
                asyncio.run(reconcile.backtest_session(session['id'], BackgroundTasks(), self.config))
            freeze.assert_not_called(); launch.assert_not_called()
            source.write_text('class Sample: pass')
            prepared = self.base / 'prepared'
            prepared.mkdir()
            (prepared / 'inputs.json').write_text(json.dumps(self.frozen() | {'files': {
                'inputs/strategies/Sample.py': session['revision'],
                'inputs/strategies/Sample.json': session['source_hashes']['strategies/Sample.json']}}))
            record = self.run_record()
            record.update(id=uuid4().hex, strategy='Sample', revision=session['revision'], status='prepared')
            freeze.return_value = prepared, record

            async def fake_launch(p, current, tasks, config, runtime):
                self.assertEqual(current['paper_reconcile']['session_id'], session['id'])
                self.assertEqual(p, prepared)
                return current
            launch.side_effect = fake_launch
            result = asyncio.run(reconcile.backtest_session(session['id'], BackgroundTasks(), self.config))
        self.assertEqual(result['paper_reconcile']['observed_start'], session['started_at'])
        self.assertTrue(result['settings']['timerange'].startswith(str(int(self.start.timestamp()))))


if __name__ == '__main__': unittest.main()
