from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from decimal import Decimal
import json

from mock import patch

from gratipay.billing.payday import Payday
from gratipay.models.participant import Participant
from gratipay.testing import Harness
from gratipay.utils.history import get_end_of_year_balance, iter_payday_events


def make_history(harness):
    alice = harness.make_participant('alice', claimed_time=datetime(2001, 1, 1, 0, 0, 0))
    harness.alice = alice
    harness.make_exchange('balanced-cc', 50, 0, alice)
    harness.make_exchange('balanced-cc', 12, 0, alice, status='failed')
    harness.make_exchange('balanced-ba', -40, 0, alice)
    harness.make_exchange('balanced-ba', -5, 0, alice, status='failed')
    harness.db.run("""
        UPDATE exchanges
           SET timestamp = "timestamp" - interval '1 year'
    """)
    harness.past_year = int(harness.db.one("""
        SELECT extract(year from timestamp)
          FROM exchanges
      ORDER BY timestamp ASC
         LIMIT 1
    """))
    harness.make_exchange('balanced-cc', 35, 0, alice)
    harness.make_exchange('balanced-cc', 49, 0, alice, status='failed')
    harness.make_exchange('balanced-ba', -15, 0, alice)
    harness.make_exchange('balanced-ba', -7, 0, alice, status='failed')


class TestHistory(Harness):

    def test_iter_payday_events(self):
        Payday.start().run()
        team = self.make_participant('team', number='plural', claimed_time='now')
        alice = self.make_participant('alice', claimed_time='now')
        self.make_exchange('balanced-cc', 10000, 0, team)
        self.make_exchange('balanced-cc', 10000, 0, alice)
        self.make_exchange('balanced-cc', -5000, 0, alice)
        self.db.run("""
            UPDATE transfers
               SET timestamp = "timestamp" - interval '1 month'
        """)
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now')
        team.add_member(bob)
        team.set_take_for(bob, Decimal('1.00'), team)
        alice.set_tip_to(bob, Decimal('5.00'))

        assert bob.balance == 0
        for i in range(2):
            with patch.object(Payday, 'fetch_card_holds') as fch:
                fch.return_value = {}
                Payday.start().run()
            self.db.run("""
                UPDATE paydays
                   SET ts_start = ts_start - interval '1 week'
                     , ts_end = ts_end - interval '1 week';
                UPDATE transfers
                   SET timestamp = "timestamp" - interval '1 week';
            """)
        bob = Participant.from_id(bob.id)
        assert bob.balance == 12

        Payday().start()
        events = list(iter_payday_events(self.db, bob))
        assert len(events) == 9
        assert events[0]['kind'] == 'totals'
        assert events[0]['given'] == 0
        assert events[0]['received'] == 12
        assert events[1]['kind'] == 'day-open'
        assert events[1]['payday_number'] == 2
        assert events[2]['balance'] == 12
        assert events[-1]['kind'] == 'day-close'
        assert events[-1]['balance'] == 0

        alice = Participant.from_id(alice.id)
        assert alice.balance == 4990
        events = list(iter_payday_events(self.db, alice))
        assert events[0]['given'] == 10
        assert len(events) == 11

        carl = Participant.from_id(carl.id)
        assert carl.balance == 0
        events = list(iter_payday_events(self.db, carl))
        assert len(events) == 0

    def test_iter_payday_events_with_failed_exchanges(self):
        alice = self.make_participant('alice', claimed_time='now')
        self.make_exchange('balanced-cc', 50, 0, alice)
        self.make_exchange('balanced-cc', 12, 0, alice, status='failed')
        self.make_exchange('balanced-ba', -40, 0, alice, status='failed')
        events = list(iter_payday_events(self.db, alice))
        assert len(events) == 5
        assert events[0]['kind'] == 'day-open'
        assert events[0]['balance'] == 50
        assert events[1]['kind'] == 'credit'
        assert events[1]['balance'] == 50
        assert events[2]['kind'] == 'charge'
        assert events[2]['balance'] == 50
        assert events[3]['kind'] == 'charge'
        assert events[3]['balance'] == 50
        assert events[4]['kind'] == 'day-close'
        assert events[4]['balance'] == 0

    def test_get_end_of_year_balance(self):
        make_history(self)
        balance = get_end_of_year_balance(self.db, self.alice, self.past_year, datetime.now().year)
        assert balance == 10


class TestExport(Harness):

    def setUp(self):
        Harness.setUp(self)
        make_history(self)

    def test_export_json(self):
        r = self.client.GET('/alice/history/export.json', auth_as='alice')
        assert json.loads(r.body)

    def test_export_json_aggregate(self):
        r = self.client.GET('/alice/history/export.json?mode=aggregate', auth_as='alice')
        assert json.loads(r.body)

    def test_export_json_past_year(self):
        r = self.client.GET('/alice/history/export.json?year=%s' % self.past_year, auth_as='alice')
        assert len(json.loads(r.body)['exchanges']) == 4

    def test_export_csv(self):
        r = self.client.GET('/alice/history/export.csv?key=exchanges', auth_as='alice')
        assert r.body.count('\n') == 5
