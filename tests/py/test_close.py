from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import date
from decimal import Decimal as D

import mock
import pytest

from liberapay.billing.payday import Payday
from liberapay.models.community import Community
from liberapay.models.participant import Participant
from liberapay.testing.mangopay import FakeTransfersHarness


class TestClosing(FakeTransfersHarness):

    # close

    def test_close_closes(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice', balance=D('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')

        alice.set_tip_to(bob, D('3.00'))
        carl.set_tip_to(alice, D('2.00'))

        team.add_member(alice)
        team.add_member(bob)
        assert len(team.get_current_takes()) == 2  # sanity check

        alice.close('downstream')

        assert carl.get_tip_to(alice)['amount'] == 0
        assert alice.balance == 0
        assert len(team.get_current_takes()) == 1

    def test_close_raises_for_unknown_disbursement_strategy(self):
        alice = self.make_participant('alice', balance=D('0.00'))
        with pytest.raises(alice.UnknownDisbursementStrategy):
            alice.close('cheese')

    def test_close_page_is_usually_available(self):
        alice = self.make_participant('alice')
        body = self.client.GET('/alice/settings/close', auth_as=alice).text
        assert 'Personal Information' in body

    def test_close_page_is_not_available_during_payday(self):
        Payday.start()
        alice = self.make_participant('alice')
        body = self.client.GET('/alice/settings/close', auth_as=alice).text
        assert 'Personal Information' not in body
        assert 'Try Again Later' in body

    def test_can_post_to_close_page(self):
        alice = self.make_participant('alice', balance=7)
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, D('10.00'))

        data = {'disburse_to': 'downstream'}
        response = self.client.PxST('/alice/settings/close', auth_as=alice, data=data)
        assert response.code == 302
        assert response.headers['Location'] == '/alice/'
        assert Participant.from_username('alice').balance == 0
        assert Participant.from_username('bob').balance == 7

    def test_cant_post_to_close_page_during_payday(self):
        Payday.start()
        alice = self.make_participant('alice')
        body = self.client.POST('/alice/settings/close', auth_as=alice).text
        assert 'Try Again Later' in body


    # dbafg - distribute_balance_as_final_gift

    def test_dbafg_distributes_balance_as_final_gift(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('6.00')
        assert Participant.from_username('carl').balance == D('4.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_needs_claimed_tips(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        bob = self.make_stub()
        carl = self.make_stub()
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            with pytest.raises(alice.NoOneToGiveFinalGiftTo):
                alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_id(bob.id).balance == D('0.00')
        assert Participant.from_id(carl.id).balance == D('0.00')
        assert Participant.from_id(alice.id).balance == D('10.00')

    def test_dbafg_gives_all_to_claimed(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_stub()
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_id(bob.id).balance == D('10.00')
        assert Participant.from_id(carl.id).balance == D('0.00')
        assert Participant.from_id(alice.id).balance == D('0.00')

    def test_dbafg_skips_zero_tips(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, D('0.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert self.db.one("SELECT count(*) FROM tips WHERE tippee=%s", (bob.id,)) == 1
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('10.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_favors_highest_tippee_in_rounding_errors(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('6.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('3.33')
        assert Participant.from_username('carl').balance == D('6.67')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_with_zero_balance_is_a_noop(self):
        alice = self.make_participant('alice', balance=D('0.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('6.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert self.db.one("SELECT count(*) FROM tips") == 2
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('0.00')
        assert Participant.from_username('alice').balance == D('0.00')


    # ctg - clear_tips_giving

    def test_ctg_clears_tips_giving(self):
        alice = self.make_participant('alice')
        alice.set_tip_to(self.make_participant('bob'), D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tipper=%s AND amount > 0",
                                    (alice.id,))
        assert ntips() == 1
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0

    def test_ctg_doesnt_duplicate_zero_tips(self):
        alice = self.make_participant('alice')
        bob = self.make_stub()
        alice.set_tip_to(bob, D('1.00'))
        alice.set_tip_to(bob, D('0.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tipper=%s", (alice.id,))
        assert ntips() == 2
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 2

    def test_ctg_doesnt_zero_when_theres_no_tip(self):
        alice = self.make_participant('alice')
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tipper=%s", (alice.id,))
        assert ntips() == 0
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0

    def test_ctg_clears_multiple_tips_giving(self):
        alice = self.make_participant('alice')
        alice.set_tip_to(self.make_participant('bob'), D('1.00'))
        alice.set_tip_to(self.make_participant('carl'), D('1.00'))
        alice.set_tip_to(self.make_participant('darcy'), D('1.00'))
        alice.set_tip_to(self.make_participant('evelyn'), D('1.00'))
        alice.set_tip_to(self.make_participant('francis'), D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tipper=%s AND amount > 0",
                                    (alice.id,))
        assert ntips() == 5
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0


    # ctr - clear_tips_receiving

    def test_ctr_clears_tips_receiving(self):
        alice = self.make_participant('alice')
        self.make_participant('bob').set_tip_to(alice, D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee=%s AND amount > 0",
                                    (alice.id,))
        assert ntips() == 1
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0

    def test_ctr_doesnt_duplicate_zero_tips(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        bob.set_tip_to(alice, D('1.00'))
        bob.set_tip_to(alice, D('0.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee=%s", (alice.id,))
        assert ntips() == 2
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 2

    def test_ctr_doesnt_zero_when_theres_no_tip(self):
        alice = self.make_participant('alice')
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee=%s", (alice.id,))
        assert ntips() == 0
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0

    def test_ctr_clears_multiple_tips_receiving(self):
        alice = self.make_stub()
        self.make_participant('bob').set_tip_to(alice, D('1.00'))
        self.make_participant('carl').set_tip_to(alice, D('2.00'))
        self.make_participant('darcy').set_tip_to(alice, D('3.00'))
        self.make_participant('evelyn').set_tip_to(alice, D('4.00'))
        self.make_participant('francis').set_tip_to(alice, D('5.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee=%s AND amount > 0",
                                    (alice.id,))
        assert ntips() == 5
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0


    # cpi - clear_personal_information

    @mock.patch.object(Participant, '_mailer')
    def test_cpi_clears_personal_information(self, mailer):
        alice = self.make_participant( 'alice'
                                     , goal=100
                                     , hide_giving=True
                                     , hide_receiving=True
                                     , avatar_url='img-url'
                                     , email='alice@example.com'
                                     , session_token='deadbeef'
                                     , session_expires='2000-01-01'
                                     , giving=20
                                     , receiving=40
                                     , npatrons=21
                                      )
        alice.upsert_statement('en', 'not forgetting to be awesome!')
        alice.add_email('alice@example.net')

        with self.db.get_cursor() as cursor:
            alice.clear_personal_information(cursor)
        new_alice = Participant.from_username('alice')

        assert alice.get_statement(['en']) == (None, None)
        assert alice.goal == new_alice.goal == None
        assert alice.hide_giving == new_alice.hide_giving == True
        assert alice.hide_receiving == new_alice.hide_receiving == True
        assert alice.avatar_url == new_alice.avatar_url == None
        assert alice.email == new_alice.email
        assert alice.giving == new_alice.giving == 0
        assert alice.receiving == new_alice.receiving == 0
        assert alice.npatrons == new_alice.npatrons == 0
        assert alice.session_token == new_alice.session_token == None
        assert alice.session_expires.year == new_alice.session_expires.year == date.today().year
        assert not alice.get_emails()

    def test_cpi_clears_communities(self):
        alice = self.make_participant('alice')
        c = alice.create_community('test')
        alice.update_community_status('memberships', True, c.id)
        bob = self.make_participant('bob')
        bob.update_community_status('memberships', True, c.id)

        assert Community.from_name('test').nmembers == 2  # sanity check

        with self.db.get_cursor() as cursor:
            alice.clear_personal_information(cursor)

        assert Community.from_name('test').nmembers == 1
