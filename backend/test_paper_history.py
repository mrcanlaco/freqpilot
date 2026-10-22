import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from freqtrade.rpc.api_server import paper_history as journal
from freqtrade.rpc.api_server.api_paper import paper_status, start_paper, pause_paper, stop_paper
import test_paper


class PaperHistoryChecks(unittest.TestCase):
    def setUp(self):
        self.fixture = test_paper.PaperChecks()
        self.fixture.setUp()
        self.config = self.fixture.config
        self.profile = self.fixture.prepared()
        self.state = {'online': True, 'state': 'stopped', 'open_trades': 0,
                      'native_strategy': self.profile['wrapper'], 'active_profile': self.profile['id'],
                      'profiles': [self.profile]}
        self.native = {'bot_name': 'configuration #one', 'password': 'NEVER_JOURNAL_ME'}

    def tearDown(self): self.fixture.tearDown()

    def test_reading_empty_history_does_not_create_database_or_invent_old_sessions(self):
        self.assertEqual(journal.history(self.config)['events'], [])
        self.assertIsNone(journal.history(self.config)['started_at'])
        self.assertFalse(journal.path(self.config).exists())

    def test_native_observations_deduplicate_and_do_not_treat_trade_count_as_lifecycle(self):
        journal.observe(self.config, self.state, self.native)
        journal.observe(self.config, self.state, self.native)
        journal.observe(self.config, {**self.state, 'open_trades': 1}, self.native)
        self.assertEqual(len(journal.history(self.config)['events']), 1)
        journal.observe(self.config, {**self.state, 'state': 'paused'}, self.native)
        journal.observe(self.config, {**self.state, 'state': 'paused'}, {'bot_name': 'configuration #two'})
        rows = journal.history(self.config)['events']
        self.assertEqual([r['kind'] for r in rows], ['observation', 'observation', 'baseline'])
        self.assertTrue(rows[0]['body']['configuration_changed'])
        self.assertEqual(rows[1]['body']['previous_state'], 'stopped')
        self.assertNotIn('NEVER_JOURNAL_ME', json.dumps(rows))
        self.assertNotIn(b'NEVER_JOURNAL_ME', journal.path(self.config).read_bytes())
        self.assertNotIn('configuration #one', json.dumps(rows))

    def test_observation_gap_never_means_stopped_or_proves_configuration_changed(self):
        journal.observe(self.config, {**self.state, 'state': 'running'}, self.native)
        gap = {'online': False, 'state': 'unavailable', 'profiles': [self.profile], 'open_trades': None}
        journal.observe(self.config, gap)
        journal.observe(self.config, gap)
        journal.observe(self.config, {**self.state, 'state': 'running'}, {'bot_name': 'configuration #other'})
        rows = journal.history(self.config)['events']
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]['kind'], 'observation_gap')
        self.assertEqual(rows[1]['profile_id'], self.profile['id'])
        self.assertIsNone(rows[1]['body']['open_trades'])
        self.assertTrue(rows[0]['body']['observation_restored'])
        self.assertFalse(rows[0]['body']['configuration_changed'])

    def test_cursor_and_filters_survive_newer_events_and_connections(self):
        for state in ('stopped', 'running', 'paused', 'running'):
            journal.observe(self.config, {**self.state, 'state': state}, self.native)
        page = journal.history(self.config, profile_id=self.profile['id'], limit=2)
        journal.observe(self.config, self.state, self.native)
        older = journal.history(self.config, profile_id=self.profile['id'], before=page['next_before'], limit=2)
        self.assertTrue(set(r['id'] for r in page['events']).isdisjoint(r['id'] for r in older['events']))
        self.assertEqual(len(older['events']), 2)
        self.assertIsNone(older['next_before'])
        self.assertEqual(journal.history(self.config, strategy='OtherStrategy')['events'], [])
        self.assertEqual(len(journal.history(self.config, strategy='PaperSample')['events']), 5)

    def test_requested_state_is_confirmed_only_from_fresh_native_profile_and_state(self):
        for observed, expected in [(self.state, 'unconfirmed'), ({**self.state, 'state': 'running'}, 'observed'),
                                   ({**self.state, 'state': 'running', 'active_profile': 'other'}, 'unconfirmed')]:
            with self.subTest(expected=expected), \
                 patch('freqtrade.rpc.api_server.api_paper.checked_native', return_value={'strategy': self.profile['wrapper']}), \
                 patch('freqtrade.rpc.api_server.api_paper.native', return_value={'status': 'starting'}), \
                 patch('freqtrade.rpc.api_server.api_paper.paper_status', return_value=observed):
                result = start_paper(self.profile['id'], self.config)
            self.assertEqual(result['action_result']['outcome'], expected)
            events = journal.history(self.config)['events']
            self.assertEqual(events[0]['kind'], 'action_result')
            self.assertEqual(events[1]['kind'], 'action_request')
            self.assertEqual(events[0]['body']['request_id'], events[1]['body']['request_id'])

    def test_rejected_switch_keeps_safety_checks_and_does_not_claim_no_worker_effect(self):
        with patch('freqtrade.rpc.api_server.api_paper.checked_native', return_value={'strategy': 'FPPaperIdle'}), \
             patch('freqtrade.rpc.api_server.api_paper.native', return_value=[{'trade_id': 1}]) as native, \
             patch('freqtrade.rpc.api_server.api_paper.reload_stopped') as reload:
            with self.assertRaises(HTTPException): start_paper(self.profile['id'], self.config)
        reload.assert_not_called()
        self.assertEqual(native.call_args.args[:2], ('GET', '/status'))
        result = journal.history(self.config)['events'][0]['body']
        self.assertEqual(result['outcome'], 'error')
        self.assertEqual(result['http_status'], 409)

    def test_journal_failure_before_request_prevents_sending_worker_command(self):
        with patch('freqtrade.rpc.api_server.paper_history.connection', side_effect=HTTPException(503, 'journal unavailable')), \
             patch('freqtrade.rpc.api_server.api_paper.checked_native') as native:
            with self.assertRaises(HTTPException): start_paper(self.profile['id'], self.config)
        native.assert_not_called()

    def test_history_error_does_not_change_known_online_execution_state(self):
        current = {'dry_run': True, 'trading_mode': 'futures', 'margin_mode': 'isolated',
                   'strategy': self.profile['wrapper'], 'state': 'stopped', 'bot_name': 'worker'}
        with patch('freqtrade.rpc.api_server.api_paper.native', side_effect=[current, []]), \
             patch('freqtrade.rpc.api_server.paper_history.observe', side_effect=HTTPException(503, 'journal unavailable')):
            result = paper_status(self.config)
        self.assertTrue(result['online'])
        self.assertEqual(result['state'], 'stopped')
        self.assertEqual(result['history_error'], 'journal unavailable')

    def test_journal_failure_does_not_block_native_pause_or_stop(self):
        for handler, expected in [(pause_paper, 'paused'), (stop_paper, 'stopped')]:
            with self.subTest(state=expected), \
                 patch('freqtrade.rpc.api_server.paper_history.connection', side_effect=HTTPException(503, 'journal unavailable')), \
                 patch('freqtrade.rpc.api_server.api_paper.checked_native'), \
                 patch('freqtrade.rpc.api_server.api_paper.native', return_value=[]) as native, \
                 patch('freqtrade.rpc.api_server.api_paper.reload_stopped') as reload, \
                 patch('freqtrade.rpc.api_server.api_paper.paper_status', return_value={**self.state, 'state': expected, 'active_profile': None}):
                result = handler(self.config)
            if expected == 'paused': self.assertEqual(native.call_args.args[:2], ('POST', '/pause'))
            else: reload.assert_called_once()
            self.assertEqual(result['state'], expected)
            self.assertFalse(result['action_result']['logged'])
            self.assertEqual(result['history_error'], 'journal unavailable')

    def test_result_write_failure_does_not_erase_native_success_or_encourage_retry(self):
        real_connection = journal.connection
        calls = 0
        def fail_result(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2: raise HTTPException(503, 'journal write failed after native call')
            return real_connection(*args, **kwargs)
        with patch('freqtrade.rpc.api_server.paper_history.connection', side_effect=fail_result), \
             patch('freqtrade.rpc.api_server.api_paper.checked_native', return_value={'strategy': self.profile['wrapper']}), \
             patch('freqtrade.rpc.api_server.api_paper.native', return_value={'status': 'starting'}), \
             patch('freqtrade.rpc.api_server.api_paper.paper_status', return_value={**self.state, 'state': 'running'}):
            result = start_paper(self.profile['id'], self.config)
        self.assertEqual(result['action_result']['outcome'], 'observed')
        self.assertFalse(result['action_result']['logged'])
        self.assertIn('history_error', result)
        self.assertEqual([r['kind'] for r in journal.history(self.config)['events']], ['action_request'])

    def test_invalid_filters_and_symlink_journal_are_rejected(self):
        for kwargs in ({'profile_id': '../config'}, {'strategy': 'x; DROP TABLE events'}, {'limit': 0}, {'before': 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(HTTPException): journal.history(self.config, **kwargs)
        p = journal.path(self.config)
        p.symlink_to(Path(self.fixture.base)/'outside.sqlite')
        with self.assertRaises(HTTPException): journal.history(self.config)


if __name__ == '__main__': unittest.main()
