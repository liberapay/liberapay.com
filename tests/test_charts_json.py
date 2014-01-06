from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import json

from gittip.billing.payday import Payday
from gittip.testing import Harness

def today():
    return datetime.datetime.utcnow().date().strftime('%Y-%m-%d')

class Tests(Harness):

    def make_participants_and_tips(self):
        alice = self.make_participant('alice', balance=10, claimed_time='now')
        bob = self.make_participant('bob', balance=10, claimed_time='now')
        self.make_participant('carl', claimed_time='now')
        self.db.run("""
            INSERT INTO EXCHANGES
                (amount, fee, participant) VALUES
                (10.00, 0.00, 'alice'),
                (10.00, 0.00, 'bob')
        """)
        self.make_participant('notactive', claimed_time='now')

        alice.set_tip_to('carl', '1.00')
        bob.set_tip_to('carl', '2.00')

        return alice, bob

    def run_payday(self):
        Payday(self.db).run()


    def test_no_payday_returns_empty_list(self):
        self.make_participants_and_tips()
        assert json.loads(self.client.GET('/carl/charts.json').body) == []

    def test_zeroth_payday_is_ignored(self):
        self.make_participants_and_tips()
        self.run_payday()   # zeroeth
        assert json.loads(self.client.GET('/carl/charts.json').body) == []

    def test_first_payday_comes_through(self):
        alice, bob = self.make_participants_and_tips()
        self.run_payday()   # zeroeth, ignored
        self.run_payday()   # first

        expected = [ { "date": today()
                     , "npatrons": 2
                     , "receipts": 3.00
                      }
                    ]
        actual = json.loads(self.client.GET('/carl/charts.json').body)

        assert actual == expected

    def test_second_payday_comes_through(self):
        alice, bob = self.make_participants_and_tips()
        self.run_payday()   # zeroth, ignored
        self.run_payday()   # first

        alice.set_tip_to('carl', '5.00')
        bob.set_tip_to('carl', '0.00')

        self.run_payday()   # second

        expected = [ { "date": today()
                     , "npatrons": 1 # most recent first
                     , "receipts": 5.00
                      }
                   , { "date": today()
                     , "npatrons": 2
                     , "receipts": 3.00
                      }
                    ]
        actual = json.loads(self.client.GET('/carl/charts.json').body)

        assert actual == expected

    def test_sandwiched_tipless_payday_comes_through(self):
        alice, bob = self.make_participants_and_tips()
        self.run_payday()   # zeroth, ignored
        self.run_payday()   # first

        # Oops! Sorry, Carl. :-(
        alice.set_tip_to('carl', '0.00')
        bob.set_tip_to('carl', '0.00')
        self.run_payday()   # second

        # Bouncing back ...
        alice.set_tip_to('carl', '5.00')
        self.run_payday()   # third

        expected = [ { "date": today()
                     , "npatrons": 1 # most recent first
                     , "receipts": 5.00
                      }
                   , { "date": today()
                     , "npatrons": 0
                     , "receipts": 0.00
                      }
                   , { "date": today()
                     , "npatrons": 2
                     , "receipts": 3.00
                      }
                    ]
        actual = json.loads(self.client.GET('/carl/charts.json').body)

        assert actual == expected

    def test_out_of_band_transfer_gets_included_with_prior_payday(self):
        alice, bob = self.make_participants_and_tips()
        self.run_payday()   # zeroth, ignored
        self.run_payday()   # first
        self.run_payday()   # second

        # Do an out-of-band transfer.
        self.db.run("UPDATE participants SET balance=balance - 4 WHERE username='alice'")
        self.db.run("UPDATE participants SET balance=balance + 4 WHERE username='carl'")
        self.db.run("INSERT INTO transfers (tipper, tippee, amount) VALUES ('alice', 'carl', 4)")

        self.run_payday()   # third

        expected = [ { "date": today()
                     , "npatrons": 2 # most recent first
                     , "receipts": 3.00
                      }
                   , { "date": today()
                     , "npatrons": 3  # Since this is rare, don't worry that we double-count alice.
                     , "receipts": 7.00
                      }
                   , { "date": today()
                     , "npatrons": 2
                     , "receipts": 3.00
                      }
                    ]
        actual = json.loads(self.client.GET('/carl/charts.json').body)

        assert actual == expected

    def test_never_received_gives_empty_array(self):
        alice, bob = self.make_participants_and_tips()
        self.run_payday()   # zeroeth, ignored
        self.run_payday()   # first
        self.run_payday()   # second
        self.run_payday()   # third

        expected = []
        actual = json.loads(self.client.GET('/alice/charts.json').body)

        assert actual == expected

    def test_transfer_volume(self):
        self.make_participants_and_tips()
        self.run_payday()
        self.run_payday()

        expected = { "date": today()
                   , "weekly_gifts": 3.0
                   , "charges": 0.0
                   , "withdrawals": 0.0
                   , "active_users": 3
                   , "total_users": 4
                   , "total_gifts": 6.0
                    }
        actual = json.loads(self.client.GET('/about/charts.json').body)[0]

        assert actual == expected
