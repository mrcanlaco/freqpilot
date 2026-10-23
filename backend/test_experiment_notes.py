"""Frozen-run annotation and protocol comparison checks, with no engine jobs."""
import json
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4
from zipfile import ZipFile

from fastapi import HTTPException
from pydantic import ValidationError

from freqtrade.rpc.api_server import api_experiment_notes as notes
from freqtrade.rpc.api_server.api_runs import digest, run_root
from freqtrade.rpc.api_server.api_studio import write_check


class ResearchNoteChecks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        (self.base / 'strategies').mkdir()
        self.config = {'user_data_dir': self.base, 'datadir': self.base, 'dry_run': True}

    def tearDown(self):
        self.tmp.cleanup()

    def make_run(self, *, fee=.0005, entry_pricing=None, source='class Sample: pass', data=b'candles',
                 timerange='20260101-20260201', actual_end='2026-02-01 00:00:00'):
        uid = uuid4().hex
        p = run_root(self.config) / uid
        strategy = p / 'inputs/strategies/Sample.py'
        market = p / 'inputs/data/binance/futures/BTC.feather'
        strategy.parent.mkdir(parents=True)
        market.parent.mkdir(parents=True)
        strategy.write_text(source)
        market.write_bytes(data)
        settings = {'timerange': timerange, 'timeframe': '1h', 'timeframe_detail': '1m',
                    'dry_run_wallet': 1000, 'stake_amount': '100', 'max_open_trades': 2,
                    'enable_protections': False}
        cfg = {'dry_run': True, 'trading_mode': 'futures', 'margin_mode': 'isolated',
               'stake_currency': 'USDT', 'fee': fee, 'liquidation_buffer': .05,
               'exchange': {'name': 'binance', 'pair_whitelist': ['BTC/USDT:USDT', 'ETH/USDT:USDT']}}
        if entry_pricing is not None:
            cfg['entry_pricing'] = entry_pricing
        config_file = p / 'inputs/config.json'
        config_file.write_text(json.dumps(cfg))
        files = {name: digest(p / name) for name in
                 ('inputs/strategies/Sample.py', 'inputs/data/binance/futures/BTC.feather', 'inputs/config.json')}
        revision = files['inputs/strategies/Sample.py']
        frozen = {'id': uid, 'strategy': 'Sample', 'revision': revision, 'engine': '2026.9',
                  'settings': settings, 'config': cfg, 'files': files}
        (p / 'inputs.json').write_text(json.dumps(frozen))
        with ZipFile(p / 'artifact.zip', 'w') as bundle:
            bundle.writestr('native.json', '{}')
        record = {'id': uid, 'strategy': 'Sample', 'revision': revision, 'engine': '2026.9',
                  'status': 'success', 'settings': settings,
                  'input_manifest_sha256': digest(p / 'inputs.json'),
                  'artifact_sha256': digest(p / 'artifact.zip'),
                  'summary': {'backtest_start': '2026-01-01 00:00:00', 'backtest_end': actual_end,
                              'total_trades': 4, 'profit_total_abs': 5}}
        write_check(p / 'record.json', record)
        return uid, p

    def test_note_is_separate_revisioned_and_bound_to_verified_archive(self):
        uid, p = self.make_run()
        empty = notes.get_note(uid, self.config)
        self.assertEqual(empty['note_revision'], 'none')
        saved = notes.put_note(uid, notes.NoteUpdate(expected_note_revision='none',
            label='Bản gốc', tags=['BTC', 'btc', ' Futures '], notes='Quan sát thêm',
            pinned_baseline=True), self.config)
        self.assertEqual(saved['tags'], ['BTC', 'Futures'])
        self.assertEqual(saved['verification'], 'passed')
        self.assertTrue(saved['pinned_baseline'])
        self.assertEqual(notes.list_notes(config=self.config)['notes'][0]['verification'], 'not_rechecked')
        with self.assertRaisesRegex(HTTPException, 'thay đổi'):
            notes.put_note(uid, notes.NoteUpdate(expected_note_revision='none', notes='Lost update'), self.config)
        updated = notes.put_note(uid, notes.NoteUpdate(expected_note_revision=saved['note_revision'],
                                                       notes='Ghi chú mới'), self.config)
        self.assertEqual(updated['label'], 'Bản gốc')
        self.assertTrue(updated['pinned_baseline'])
        self.assertEqual(updated['notes'], 'Ghi chú mới')
        self.assertNotEqual(updated['note_revision'], saved['note_revision'])
        # Notes live outside the native archive/snapshot, which remain byte-identical.
        self.assertEqual(digest(p / 'artifact.zip'), saved['artifact_sha256'])
        (p / 'artifact.zip').write_bytes(b'tampered')
        with self.assertRaises(HTTPException):
            notes.get_note(uid, self.config)

    def test_comparison_allows_source_changes_but_rejects_fee_data_and_actual_date(self):
        a, _ = self.make_run(source='class Sample: pass')
        b, _ = self.make_run(source='class Sample: changed')
        same = notes.compare(notes.CompareRequest(run_ids=[a, b]), self.config)
        self.assertTrue(same['comparable'])
        self.assertFalse(same['differences'])
        self.assertNotEqual(same['runs'][0]['source_revision'], same['runs'][1]['source_revision'])
        self.assertEqual(len(same['protocol_hash']), 64)
        c, _ = self.make_run(fee=.0008)
        d, _ = self.make_run(data=b'different candles')
        e, _ = self.make_run(actual_end='2026-01-31 18:00:00')
        f, _ = self.make_run(entry_pricing={'price_side': 'other'})
        self.assertIn('fee', notes.compare(notes.CompareRequest(run_ids=[a, c]), self.config)['differences'])
        self.assertIn('data_sha256', notes.compare(notes.CompareRequest(run_ids=[a, d]), self.config)['differences'])
        self.assertIn('native_backtest_end', notes.compare(notes.CompareRequest(run_ids=[a, e]), self.config)['differences'])
        self.assertIn('execution_config_sha256', notes.compare(notes.CompareRequest(run_ids=[a, f]), self.config)['differences'])

    def test_unknown_fee_never_declared_comparable_and_partial_run_is_rejected(self):
        a, _ = self.make_run(fee=None)
        b, _ = self.make_run(fee=None)
        answer = notes.compare(notes.CompareRequest(run_ids=[a, b]), self.config)
        self.assertFalse(answer['comparable'])
        self.assertIn('fee', answer['missing_fields'])
        c, p = self.make_run()
        record = json.loads((p / 'record.json').read_text())
        record['status'] = 'failed'
        write_check(p / 'record.json', record)
        with self.assertRaises(HTTPException):
            notes.put_note(c, notes.NoteUpdate(expected_note_revision='none', label='No'), self.config)

    def test_invalid_or_duplicated_ids_and_tag_constraints(self):
        a, _ = self.make_run()
        with self.assertRaises(HTTPException):
            notes.get_note('../other', self.config)
        with self.assertRaisesRegex(HTTPException, 'khác nhau'):
            notes.compare(notes.CompareRequest(run_ids=[a, a]), self.config)
        with self.assertRaises(ValidationError):
            notes.NoteUpdate(expected_note_revision='bad', tags=['valid'])
        with self.assertRaises(ValidationError):
            notes.NoteUpdate(expected_note_revision='none', tags=['line\nbreak'])


if __name__ == '__main__':
    unittest.main()
