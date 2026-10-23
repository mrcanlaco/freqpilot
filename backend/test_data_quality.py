"""Offline tests for raw coverage, event funding and isolated repair."""
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import requests
from fastapi import BackgroundTasks, HTTPException
from freqtrade.rpc.api_server import api_data_quality as data_quality_module
from freqtrade.rpc.api_server.webserver_bgwork import ApiBG

from freqtrade.rpc.api_server.api_data_quality import (
    RepairRequest, _binance_events, _file, _run_repair, get_quality_audit, get_repair,
    guard_research, list_repairs, quality_report, repair_preview, start_repair,
)


class FakeResponse:
    def __init__(self, rows):
        self.rows = rows

    def raise_for_status(self):
        pass

    def json(self):
        return self.rows


class FakeSession:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def get(self, url, params, timeout):
        self.calls.append(params)
        rows = [x for x in self.events if params['startTime'] <= x['fundingTime'] <= params['endTime']]
        return FakeResponse(rows[:params['limit']])


class DataQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.config = {'user_data_dir': base / 'user_data', 'datadir': base / 'data',
                       'dataformat_ohlcv': 'feather', 'dry_run': True,
                       'exchange': {'name': 'binance', 'pair_whitelist': ['BTC/USDT:USDT']}}
        (base / 'user_data' / 'strategies').mkdir(parents=True)
        self.start = pd.Timestamp('2026-10-01T00:00:00Z')
        self.dates = pd.date_range(self.start, periods=96, freq='1h')
        self.futures = self._candles(self.dates)
        self.mark = self._candles(self.dates, mark=True)
        # Three deliberately irregular events, not a presumed 8-hour schedule.
        self.events = [self.start + pd.Timedelta(hours=x) for x in (7, 21, 37, 62, 82)]
        self.funding = pd.DataFrame({'date': self.events,
                                     'funding_rate': [0.00001, -0.00002, 0.00003, 0.0, 0.00007]})
        self._write('futures', self.futures)
        self._write('mark', self.mark)
        self._write('funding_rate', self.funding)

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _candles(dates, mark=False):
        return pd.DataFrame({'date': dates, 'open': [100.] * len(dates),
                             'high': [102.] * len(dates), 'low': [99.] * len(dates),
                             'close': [101.] * len(dates),
                             'volume': [0. if mark else 1.] * len(dates)})

    def _write(self, kind, frame):
        path = _file(self.config, 'BTC/USDT:USDT', '1h', kind)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.reset_index(drop=True).to_feather(path)
        return path

    def _report(self, **kwargs):
        return quality_report(self.config, '20261002-20261004', '1h', '1h', 2,
                              persist=False, **kwargs)

    def test_complete_raw_data_has_unknown_funding_until_public_event_check(self):
        report = self._report()
        self.assertEqual(report['status'], 'unknown')
        self.assertTrue(all(row['status'] == 'ok' for row in report['files']))
        self.assertEqual(report['coverage']['base_warmup_start'], '2026-10-01T22:00:00+00:00')
        self.assertEqual(len(report['files']), 3)
        self.assertTrue(all(row['sha256'] for row in report['files']))

    def test_missing_middle_and_warmup_and_end_are_reported_exactly(self):
        broken = self.futures[self.futures['date'] != pd.Timestamp('2026-10-02T06:00:00Z')]
        broken = broken[broken['date'] >= pd.Timestamp('2026-10-02T00:00:00Z')]
        broken = broken[broken['date'] < pd.Timestamp('2026-10-03T21:00:00Z')]
        self._write('futures', broken)
        row = next(x for x in self._report()['files'] if x['type'] == 'futures')
        by_code = {x['code']: x for x in row['issues']}
        self.assertEqual(row['status'], 'missing')
        self.assertEqual(by_code['start_missing']['start'], '2026-10-01T22:00:00+00:00')
        self.assertEqual(by_code['middle_gap']['start'], '2026-10-02T06:00:00+00:00')
        self.assertEqual(by_code['middle_gap']['count'], 1)
        self.assertEqual(by_code['end_missing']['end'], '2026-10-04T00:00:00+00:00')

    def test_duplicate_bad_ohlc_nonfinite_and_mark_zero_volume(self):
        broken = pd.concat([self.futures, self.futures.iloc[[2]]], ignore_index=True)
        broken.loc[3, 'high'] = 90.
        broken.loc[4, 'close'] = float('inf')
        self._write('futures', broken)
        report = self._report()
        row = next(x for x in report['files'] if x['type'] == 'futures')
        self.assertEqual(row['status'], 'invalid')
        self.assertTrue({'timestamp_duplicate', 'ohlc_invalid', 'nonfinite'}.issubset({x['code'] for x in row['issues']}))
        mark = next(x for x in report['files'] if x['type'] == 'mark')
        self.assertEqual(mark['status'], 'ok')

    def test_funding_uses_binance_events_instead_of_fixed_interval(self):
        rows = [{'fundingTime': int(t.timestamp() * 1000), 'fundingRate': str(rate)}
                for t, rate in zip(self.events, self.funding['funding_rate'])]
        fake = FakeSession(rows)
        report = self._report(verify_funding=True, session=fake)
        self.assertEqual(report['status'], 'ok')
        self.assertEqual(report['funding_verification']['pairs'][0]['events_binance'], 2)
        self.assertEqual(report['funding_verification']['pairs'][0]['pages'], 1)
        self.assertEqual(fake.calls[0]['endTime'], int(pd.Timestamp('2026-10-04T00:00:00Z').timestamp() * 1000) - 1)
        missing = self.funding[self.funding['date'] != self.events[2]]
        self._write('funding_rate', missing)
        report = self._report(verify_funding=True, session=fake)
        self.assertEqual(report['status'], 'missing')
        self.assertEqual(report['funding_verification']['pairs'][0]['issues'][0]['code'], 'funding_events_missing')

    def test_funding_four_millisecond_native_rounding_is_one_to_one(self):
        local_events = [(self.events[2], 0.00003), (self.events[3], 0.0)]
        remote = [{'fundingTime': int(t.timestamp() * 1000) + 4, 'fundingRate': str(rate)}
                  for t, rate in local_events]
        remote[1]['fundingTime'] += 2  # another real Binance case: +6 ms
        aligned = self._report(verify_funding=True, session=FakeSession(remote))
        pair = aligned['funding_verification']['pairs'][0]
        self.assertEqual(aligned['status'], 'ok')
        self.assertEqual(aligned['funding_verification']['time_tolerance_ms'], 10)
        self.assertEqual((pair['events_binance'], pair['events_local']), (2, 2))
        self.assertEqual(pair['issues'], [])

        wrong_rate = [dict(x) for x in remote]
        wrong_rate[0]['fundingRate'] = '0.00004'
        changed = self._report(verify_funding=True, session=FakeSession(wrong_rate))
        self.assertEqual(changed['status'], 'invalid')
        self.assertEqual(changed['funding_verification']['pairs'][0]['issues'][0]['code'],
                         'funding_events_different')

        outside_tolerance = [dict(x) for x in remote]
        outside_tolerance[0]['fundingTime'] += 7  # +11 ms must not match a whole-second local event
        missed = self._report(verify_funding=True, session=FakeSession(outside_tolerance))
        self.assertEqual(missed['status'], 'invalid')  # missing Binance event + unmatched local event
        self.assertIn('funding_events_missing', {x['code'] for x in missed['issues']})

    def test_funding_near_duplicate_remote_or_local_is_invalid(self):
        stamp = int(self.events[2].timestamp() * 1000)
        rows = [{'fundingTime': stamp + 2, 'fundingRate': '0.00003'},
                {'fundingTime': stamp + 4, 'fundingRate': '0.00003'}]
        report = self._report(verify_funding=True, session=FakeSession(rows))
        self.assertEqual(report['status'], 'invalid')
        self.assertEqual(report['funding_verification']['pairs'][0]['issues'][0]['code'],
                         'funding_events_duplicate')
        local_dup = pd.concat([self.funding, pd.DataFrame({
            'date': [self.events[2] + pd.Timedelta(milliseconds=4)], 'funding_rate': [0.00003]})],
            ignore_index=True).sort_values('date')
        self._write('funding_rate', local_dup)
        single = [{'fundingTime': stamp + 4, 'fundingRate': '0.00003'}]
        report = self._report(verify_funding=True, session=FakeSession(single))
        self.assertEqual(report['status'], 'invalid')
        self.assertEqual(report['funding_verification']['pairs'][0]['issues'][0]['code'],
                         'funding_events_duplicate')

    def test_funding_public_pagination_and_offline_unknown(self):
        start = datetime(2026, 10, 1, tzinfo=timezone.utc)
        events = [{'fundingTime': int(start.timestamp() * 1000) + x * 1000,
                   'fundingRate': '0.00001'} for x in range(1002)]
        session = FakeSession(events)
        result, pages = _binance_events('BTCUSDT', start, datetime(2026, 10, 2, tzinfo=timezone.utc), session)
        self.assertEqual((len(result), pages), (1002, 2))
        class BrokenSession:
            def get(self, *args, **kwargs):
                raise requests.ConnectionError('offline')
        report = self._report(verify_funding=True, session=BrokenSession())
        self.assertEqual(report['status'], 'unknown')
        self.assertEqual(report['funding_verification']['status'], 'unknown')

    def test_preview_requires_explicit_start_and_stale_source_is_rejected(self):
        self._write('mark', self.mark[self.mark['date'] != self.dates[32]])
        preview = repair_preview('20261002-20261004', '1h', '1h', 2, False, self.config)
        self.assertEqual(preview['status'], 'ready')
        self.assertEqual([(x['type'], x['timeframe']) for x in preview['operations']], [('mark', '1h')])
        self._write('mark', self.mark)
        with self.assertRaises(HTTPException) as ctx:
            start_repair(RepairRequest(preview_id=preview['id']), BackgroundTasks(), self.config)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_audit_marks_changed_input_stale_and_interrupted_job_does_not_resume(self):
        report = quality_report(self.config, '20261002-20261004', '1h', '1h', 2, False)
        self.assertTrue(get_quality_audit(report['id'], self.config)['is_current'])
        self._write('mark', self.mark[self.mark['date'] != self.dates[32]])
        stale = get_quality_audit(report['id'], self.config)
        self.assertFalse(stale['is_current'])
        self.assertEqual(stale['stale_files'][0]['type'], 'mark')
        preview = repair_preview('20261002-20261004', '1h', '1h', 2, False, self.config)
        record = start_repair(RepairRequest(preview_id=preview['id']), BackgroundTasks(), self.config)
        with self.assertRaises(HTTPException) as ctx:
            guard_research(self.config)
        self.assertEqual(ctx.exception.status_code, 409)
        data_quality_module._active_job = None  # emulate webserver restart
        ApiBG.download_data_running = False
        jobs = list_repairs(self.config)['jobs']
        self.assertEqual(jobs[0]['id'], record['id'])
        self.assertEqual(jobs[0]['status'], 'interrupted')

    def test_isolated_repair_keeps_live_data_when_candidate_fails_then_promotes_valid(self):
        original = self.mark[self.mark['date'] != self.dates[32]]
        live = self._write('mark', original)
        before = live.read_bytes()
        preview = repair_preview('20261002-20261004', '1h', '1h', 2, False, self.config)
        tasks = BackgroundTasks()
        record = start_repair(RepairRequest(preview_id=preview['id']), tasks, self.config)

        def write_staged(config, op, staging):
            stage_config = {**config, 'datadir': staging}
            file = _file(stage_config, op['pair'], op['timeframe'], op['type'])
            file.parent.mkdir(parents=True, exist_ok=True)
            self.mark.reset_index(drop=True).to_feather(file)

        with patch('freqtrade.rpc.api_server.api_data_quality._native_download', side_effect=write_staged), \
             patch('freqtrade.rpc.api_server.api_data_quality._verify_funding', return_value={
                 'status': 'unknown', 'reason': 'offline', 'pairs': [], 'source': 'test', 'checked_at': None}):
            _run_repair(record['id'], self.config)
        failed = get_repair(record['id'], self.config)
        self.assertEqual(failed['status'], 'failed')
        self.assertEqual(live.read_bytes(), before)
        preview2 = repair_preview('20261002-20261004', '1h', '1h', 2, False, self.config)
        record2 = start_repair(RepairRequest(preview_id=preview2['id']), BackgroundTasks(), self.config)
        with patch('freqtrade.rpc.api_server.api_data_quality._native_download', side_effect=write_staged), \
             patch('freqtrade.rpc.api_server.api_data_quality._verify_funding', return_value={
                 'status': 'ok', 'reason': None, 'pairs': [{'pair': 'BTC/USDT:USDT', 'status': 'ok', 'issues': []}],
                 'source': 'test', 'checked_at': None}):
            _run_repair(record2['id'], self.config)
        done = get_repair(record2['id'], self.config)
        self.assertEqual(done['status'], 'success', done['error'])
        self.assertEqual(done['promoted_files'], 1)
        self.assertEqual(len(pd.read_feather(live)), len(self.mark))


if __name__ == '__main__':
    unittest.main()
