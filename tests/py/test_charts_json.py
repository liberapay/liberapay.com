from __future__ import absolute_import, division, print_function, unicode_literals

import datetime
import json

from mock import patch

from gittip.billing.payday import Payday
from gittip.testing import Harness

def today():
    return datetime.datetime.utcnow().date().strftime('%Y-%m-%d')

class TestChartsJson(Harness):

    def setUp(self):
        Harness.setUp(self)

        self.alice = self.make_participant('alice', claimed_time='now')
        self.bob = self.make_participant('bob', claimed_time='now')
        self.carl = self.make_participant('carl', claimed_time='now')
        self.make_exchange('bill', 10, 0, self.alice)
        self.make_exchange('bill', 10, 0, self.bob)
        self.make_participant('notactive', claimed_time='now')

        self.alice.set_tip_to(self.carl, '1.00')
        self.bob.set_tip_to(self.carl, '2.00')

    def run_payday(self):
        with patch.object(Payday, 'fetch_card_holds') as fch:
            fch.return_value = {}
            Payday.start().run()


    def test_no_payday_returns_empty_list(self):
        assert json.loads(self.client.GET('/carl/charts.json').body) == []

    def test_zeroth_payday_is_ignored(self):
        self.run_payday()   # zeroeth
        assert json.loads(self.client.GET('/carl/charts.json').body) == []

    def test_first_payday_comes_through(self):
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
        self.run_payday()   # zeroth, ignored
        self.run_payday()   # first

        self.alice.set_tip_to(self.carl, '5.00')
        self.bob.set_tip_to(self.carl, '0.00')

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
        self.run_payday()   # zeroth, ignored
        self.run_payday()   # first

        # Oops! Sorry, Carl. :-(
        self.alice.set_tip_to(self.carl, '0.00')
        self.bob.set_tip_to(self.carl, '0.00')
        self.run_payday()   # second

        # Bouncing back ...
        self.alice.set_tip_to(self.carl, '5.00')
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
        self.run_payday()   # zeroth, ignored
        self.run_payday()   # first
        self.run_payday()   # second

        # Do an out-of-band transfer.
        self.db.run("UPDATE participants SET balance=balance - 4 WHERE username='alice'")
        self.db.run("UPDATE participants SET balance=balance + 4 WHERE username='carl'")
        self.db.run("INSERT INTO transfers (tipper, tippee, amount, context) "
                    "VALUES ('alice', 'carl', 4, 'tip')")

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
        self.run_payday()   # zeroeth, ignored
        self.run_payday()   # first
        self.run_payday()   # second
        self.run_payday()   # third

        expected = []
        actual = json.loads(self.client.GET('/alice/charts.json').body)

        assert actual == expected

    def test_transfer_volume(self):
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
