from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from decimal import Decimal
import json

from liberapay.billing.payday import Payday
from liberapay.models.participant import Participant
from liberapay.testing import Harness
from liberapay.testing.mangopay import FakeTransfersHarness
from liberapay.utils.history import get_end_of_year_balance, iter_payday_events


def make_history(harness):
    alice = harness.make_participant('alice', join_time=datetime(2001, 1, 1, 0, 0, 0))
    harness.alice = alice
    harness.make_exchange('mango-cc', 50, 0, alice)
    harness.make_exchange('mango-cc', 12, 0, alice, status='failed')
    harness.make_exchange('mango-ba', -40, 0, alice)
    harness.make_exchange('mango-ba', -5, 0, alice, status='failed')
    harness.db.run("""
        UPDATE exchanges
           SET timestamp = "timestamp" - interval '1 year';
        UPDATE cash_bundles
           SET ts = ts - interval '1 year';
    """)
    harness.past_year = int(harness.db.one("""
        SELECT extract(year from timestamp)
          FROM exchanges
      ORDER BY id ASC
         LIMIT 1
    """))
    harness.make_exchange('mango-cc', 35, 0, alice)
    harness.make_exchange('mango-cc', 49, 0, alice, status='failed')
    harness.make_exchange('mango-ba', -15, 0, alice)
    harness.make_exchange('mango-ba', -7, 0, alice, status='failed')


class TestHistory(FakeTransfersHarness):

    def test_iter_payday_events(self):
        now = datetime.now()
        Payday.start().run()
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice')
        self.make_exchange('mango-cc', 10000, 0, alice)
        self.make_exchange('mango-cc', -5000, 0, alice)
        self.db.run("""
            UPDATE transfers
               SET timestamp = "timestamp" - interval '1 month'
        """)
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        david = self.make_participant('david')
        self.make_exchange('mango-cc', 10000, 0, david)
        david.set_tip_to(team, Decimal('1.00'))
        team.set_take_for(bob, Decimal('1.00'), bob)
        alice.set_tip_to(bob, Decimal('5.00'))

        assert bob.balance == 0
        for i in range(2):
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

        # Make sure events are all in the same year
        delta = '%s days' % (364 - (now - datetime(now.year, 1, 1)).days)
        self.db.run("""
            UPDATE paydays
               SET ts_start = ts_start + interval %(delta)s
                 , ts_end = ts_end + interval %(delta)s;
            UPDATE transfers
               SET timestamp = "timestamp" + interval %(delta)s;
        """, dict(delta=delta))

        events = list(iter_payday_events(self.db, bob, now.year))
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
        events = list(iter_payday_events(self.db, alice, now.year))
        assert events[0]['given'] == 10
        assert len(events) == 11

        carl = Participant.from_id(carl.id)
        assert carl.balance == 0
        events = list(iter_payday_events(self.db, carl, now.year))
        assert len(events) == 0

    def test_iter_payday_events_with_failed_exchanges(self):
        alice = self.make_participant('alice')
        self.make_exchange('mango-cc', 50, 0, alice)
        self.make_exchange('mango-cc', 12, 0, alice, status='failed')
        self.make_exchange('mango-ba', -40, 0, alice, status='failed')
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
        r = self.client.GET('/alice/wallet/export.json', auth_as=self.alice)
        assert json.loads(r.body)

    def test_export_json_aggregate(self):
        r = self.client.GET('/alice/wallet/export.json?mode=aggregate', auth_as=self.alice)
        assert json.loads(r.body)

    def test_export_json_past_year(self):
        r = self.client.GET('/alice/wallet/export.json?year=%s' % self.past_year, auth_as=self.alice)
        assert len(json.loads(r.body)['exchanges']) == 4

    def test_export_csv(self):
        r = self.client.GET('/alice/wallet/export.csv?key=exchanges', auth_as=self.alice)
        assert r.body.count('\n') == 5
