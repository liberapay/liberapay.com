from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal

from gittip.billing.payday import Payday
from gittip.testing import Harness
from gittip.utils.history import iter_payday_events


class TestHistory(Harness):

    def test_iter_payday_events_counts_correctly(self):
        team = self.make_participant('team', number='plural', claimed_time='now', balance=10000)
        alice = self.make_participant('alice', claimed_time='now', balance=10000)
        self.db.run("""
            INSERT INTO exchanges
                        (amount, fee, participant)
                 VALUES (10000, 0, 'team')
                      , (10000, 0, 'alice');
        """)
        bob = self.make_participant('bob', claimed_time='now')
        team.add_member(bob)
        team.set_take_for(bob, Decimal('1.00'), team)
        alice.set_tip_to(bob, Decimal('5.00'))
        for i in range(3):
            Payday(self.db).run()
        Payday(self.db).start()
        event = next(iter_payday_events(self.db, bob))
        assert event['event'] == 'payday-start'
        assert event['number'] == 2
