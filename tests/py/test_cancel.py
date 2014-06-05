from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D

from gittip.testing import Harness


class Tests(Harness):

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
