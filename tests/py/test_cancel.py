from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

import pytest
from gittip.models.participant import Participant
from gittip.testing import Harness


class Tests(Harness):

    # dbafg - distribute_balance_as_final_gift

    def test_dbafg_distributes_balance_as_final_gift(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        self.make_participant('bob', claimed_time='now')
        self.make_participant('carl', claimed_time='now')
        alice.set_tip_to('bob', D('3.00'))
        alice.set_tip_to('carl', D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('6.00')
        assert Participant.from_username('carl').balance == D('4.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_needs_claimed_tips(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        self.make_participant('bob')
        self.make_participant('carl')
        alice.set_tip_to('bob', D('3.00'))
        alice.set_tip_to('carl', D('2.00'))
        with self.db.get_cursor() as cursor:
            with pytest.raises(alice.NoOneToGiveFinalGiftTo):
                alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('0.00')
        assert Participant.from_username('alice').balance == D('10.00')

    def test_dbafg_gives_all_to_claimed(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        self.make_participant('bob', claimed_time='now')
        self.make_participant('carl')
        alice.set_tip_to('bob', D('3.00'))
        alice.set_tip_to('carl', D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('10.00')
        assert Participant.from_username('carl').balance == D('0.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_skips_zero_tips(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        self.make_participant('bob', claimed_time='now')
        self.make_participant('carl', claimed_time='now')
        alice.set_tip_to('bob', D('0.00'))
        alice.set_tip_to('carl', D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert self.db.one("SELECT count(*) FROM tips WHERE tippee='bob'") == 1
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('10.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_favors_highest_tippee_in_rounding_errors(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        self.make_participant('bob', claimed_time='now')
        self.make_participant('carl', claimed_time='now')
        alice.set_tip_to('bob', D('3.00'))
        alice.set_tip_to('carl', D('6.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('3.33')
        assert Participant.from_username('carl').balance == D('6.67')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_with_zero_balance_is_a_noop(self):
        alice = self.make_participant('alice', balance=D('0.00'))
        self.make_participant('bob', claimed_time='now')
        self.make_participant('carl', claimed_time='now')
        alice.set_tip_to('bob', D('3.00'))
        alice.set_tip_to('carl', D('6.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert self.db.one("SELECT count(*) FROM tips") == 2
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('0.00')
        assert Participant.from_username('alice').balance == D('0.00')


    # ctr - clear_tips_receiving

    def test_ctr_clears_tips_receiving(self):
        alice = self.make_participant('alice')
        self.make_participant('bob').set_tip_to('alice', D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee='alice' AND amount > 0")
        assert ntips() == 1
        alice.clear_tips_receiving()
        assert ntips() == 0

    def test_ctr_doesnt_duplicate_zero_tips(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        bob.set_tip_to('alice', D('1.00'))
        bob.set_tip_to('alice', D('0.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee='alice'")
        assert ntips() == 2
        alice.clear_tips_receiving()
        assert ntips() == 2

    def test_ctr_doesnt_zero_when_theres_no_tip(self):
        alice = self.make_participant('alice')
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee='alice'")
        assert ntips() == 0
        alice.clear_tips_receiving()
        assert ntips() == 0

    def test_ctr_clears_multiple_tips_receiving(self):
        alice = self.make_participant('alice')
        self.make_participant('bob').set_tip_to('alice', D('1.00'))
        self.make_participant('carl').set_tip_to('alice', D('2.00'))
        self.make_participant('darcy').set_tip_to('alice', D('3.00'))
        self.make_participant('evelyn').set_tip_to('alice', D('4.00'))
        self.make_participant('francis').set_tip_to('alice', D('5.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee='alice' AND amount > 0")
        assert ntips() == 5
        alice.clear_tips_receiving()
        assert ntips() == 0
