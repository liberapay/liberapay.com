from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal

from mock import patch

from gittip.billing.payday import Payday
from gittip.models.participant import Participant
from gittip.testing import Harness
from gittip.utils.history import iter_payday_events


class TestHistory(Harness):

    def test_iter_payday_events(self):
        Payday.start().run()
        team = self.make_participant('team', number='plural', claimed_time='now', balance=10000)
        alice = self.make_participant('alice', claimed_time='now', balance=5000)
        self.db.run("""
            INSERT INTO exchanges
                        (amount, fee, participant, timestamp)
                 VALUES (10000, 0, 'team', now() - interval '1 month')
                      , (10000, 0, 'alice', now() - interval '1 month')
                      , (-5000, 0, 'alice', now() - interval '1 month');
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
        assert len(events) == 8
        assert events[0]['kind'] == 'day-open'
        assert events[0]['payday_number'] == 2
        assert events[1]['balance'] == 12
        assert events[-1]['kind'] == 'day-close'
        assert events[-1]['balance'] == '0.00'

        alice = Participant.from_id(alice.id)
        assert alice.balance == 4990
        events = list(iter_payday_events(self.db, alice))
        assert len(events) == 10

        carl = Participant.from_id(carl.id)
        assert carl.balance == 0
        events = list(iter_payday_events(self.db, carl))
        assert len(events) == 0
