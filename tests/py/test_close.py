from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import date
from decimal import Decimal as D

import balanced
import pytest
from gratipay.billing.payday import Payday
from gratipay.exceptions import NoBalancedCustomerHref, NotWhitelisted
from gratipay.models.community import Community
from gratipay.models.participant import Participant
from gratipay.testing import Harness


class TestClosing(Harness):

    # close

    def test_close_closes(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('10.00'))
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now')

        alice.set_tip_to(bob, D('3.00'))
        carl.set_tip_to(alice, D('2.00'))

        alice.close('downstream')

        assert carl.get_tip_to('alice')['amount'] == 0
        assert alice.balance == 0

    def test_close_raises_for_unknown_disbursement_strategy(self):
        alice = self.make_participant('alice', balance=D('0.00'))
        with pytest.raises(alice.UnknownDisbursementStrategy):
            alice.close('cheese')

    def test_close_page_is_usually_available(self):
        self.make_participant('alice', claimed_time='now')
        body = self.client.GET('/alice/account/close', auth_as='alice').body
        assert 'Personal Information' in body

    def test_close_page_is_not_available_during_payday(self):
        Payday.start()
        self.make_participant('alice', claimed_time='now')
        body = self.client.GET('/alice/account/close', auth_as='alice').body
        assert 'Personal Information' not in body
        assert 'Try Again Later' in body

    def test_can_post_to_close_page(self):
        alice = self.make_participant('alice', claimed_time='now', balance=7)
        bob = self.make_participant('bob', claimed_time='now')
        alice.set_tip_to(bob, D('10.00'))

        data = {'disbursement_strategy': 'downstream'}
        response = self.client.PxST('/alice/account/close', auth_as='alice', data=data)
        assert response.code == 302
        assert response.headers['Location'] == '/alice/'
        assert Participant.from_username('alice').balance == 0
        assert Participant.from_username('bob').balance == 7

    def test_cant_post_to_close_page_during_payday(self):
        Payday.start()
        self.make_participant('alice', claimed_time='now')
        body = self.client.POST('/alice/account/close', auth_as='alice').body
        assert 'Try Again Later' in body


    # wbtba - withdraw_balance_to_bank_account

    def test_wbtba_withdraws_balance_to_bank_account(self):
        alice = self.make_participant( 'alice'
                                     , balance=D('10.00')
                                     , is_suspicious=False
                                     , balanced_customer_href='new'
                                      )

        bank_account = balanced.BankAccount( name='Alice G. Krebs'
                                           , routing_number='321174851'
                                           , account_number='9900000001'
                                           , account_type='checking'
                                            ).save()
        bank_account.associate_to_customer(alice.balanced_customer_href)

        alice.close('bank')

    def test_wbtba_raises_NoBalancedCustomerHref_if_no_balanced_customer_href(self):
        alice = self.make_participant('alice', balance=D('10.00'), is_suspicious=False)
        with self.db.get_cursor() as cursor:
            with pytest.raises(NoBalancedCustomerHref):
                alice.withdraw_balance_to_bank_account(cursor)

    def test_wbtba_raises_NotWhitelisted_if_not_whitelisted(self):
        alice = self.make_participant('alice', balance=D('10.00'))
        with self.db.get_cursor() as cursor:
            with pytest.raises(NotWhitelisted):
                alice.withdraw_balance_to_bank_account(cursor)

    def test_wbtba_raises_NotWhitelisted_if_blacklisted(self):
        alice = self.make_participant('alice', balance=D('10.00'), is_suspicious=True)
        with self.db.get_cursor() as cursor:
            with pytest.raises(NotWhitelisted):
                alice.withdraw_balance_to_bank_account(cursor)


    # dbafg - distribute_balance_as_final_gift

    def test_dbafg_distributes_balance_as_final_gift(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('10.00'))
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('6.00')
        assert Participant.from_username('carl').balance == D('4.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_needs_claimed_tips(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            with pytest.raises(alice.NoOneToGiveFinalGiftTo):
                alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('0.00')
        assert Participant.from_username('alice').balance == D('10.00')

    def test_dbafg_gives_all_to_claimed(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('10.00'))
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('10.00')
        assert Participant.from_username('carl').balance == D('0.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_skips_zero_tips(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('10.00'))
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now')
        alice.set_tip_to(bob, D('0.00'))
        alice.set_tip_to(carl, D('2.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert self.db.one("SELECT count(*) FROM tips WHERE tippee='bob'") == 1
        assert Participant.from_username('bob').balance == D('0.00')
        assert Participant.from_username('carl').balance == D('10.00')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_favors_highest_tippee_in_rounding_errors(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('10.00'))
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now')
        alice.set_tip_to(bob, D('3.00'))
        alice.set_tip_to(carl, D('6.00'))
        with self.db.get_cursor() as cursor:
            alice.distribute_balance_as_final_gift(cursor)
        assert Participant.from_username('bob').balance == D('3.33')
        assert Participant.from_username('carl').balance == D('6.67')
        assert Participant.from_username('alice').balance == D('0.00')

    def test_dbafg_with_zero_balance_is_a_noop(self):
        alice = self.make_participant('alice', claimed_time='now', balance=D('0.00'))
        bob = self.make_participant('bob', claimed_time='now')
        carl = self.make_participant('carl', claimed_time='now')
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
        alice = self.make_participant('alice', claimed_time='now', last_bill_result='')
        alice.set_tip_to(self.make_participant('bob', claimed_time='now').username, D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tipper='alice' AND amount > 0")
        assert ntips() == 1
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0

    def test_ctg_doesnt_duplicate_zero_tips(self):
        alice = self.make_participant('alice', claimed_time='now')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, D('1.00'))
        alice.set_tip_to(bob, D('0.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tipper='alice'")
        assert ntips() == 2
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 2

    def test_ctg_doesnt_zero_when_theres_no_tip(self):
        alice = self.make_participant('alice')
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tipper='alice'")
        assert ntips() == 0
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0

    def test_ctg_clears_multiple_tips_giving(self):
        alice = self.make_participant('alice', claimed_time='now')
        alice.set_tip_to(self.make_participant('bob', claimed_time='now').username, D('1.00'))
        alice.set_tip_to(self.make_participant('carl', claimed_time='now').username, D('1.00'))
        alice.set_tip_to(self.make_participant('darcy', claimed_time='now').username, D('1.00'))
        alice.set_tip_to(self.make_participant('evelyn', claimed_time='now').username, D('1.00'))
        alice.set_tip_to(self.make_participant('francis', claimed_time='now').username, D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tipper='alice' AND amount > 0")
        assert ntips() == 5
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0


    # ctr - clear_tips_receiving

    def test_ctr_clears_tips_receiving(self):
        alice = self.make_participant('alice')
        self.make_participant('bob', claimed_time='now').set_tip_to(alice, D('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee='alice' AND amount > 0")
        assert ntips() == 1
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0

    def test_ctr_doesnt_duplicate_zero_tips(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob', claimed_time='now')
        bob.set_tip_to(alice, D('1.00'))
        bob.set_tip_to(alice, D('0.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee='alice'")
        assert ntips() == 2
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 2

    def test_ctr_doesnt_zero_when_theres_no_tip(self):
        alice = self.make_participant('alice')
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee='alice'")
        assert ntips() == 0
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0

    def test_ctr_clears_multiple_tips_receiving(self):
        alice = self.make_participant('alice')
        self.make_participant('bob', claimed_time='now').set_tip_to(alice, D('1.00'))
        self.make_participant('carl', claimed_time='now').set_tip_to(alice, D('2.00'))
        self.make_participant('darcy', claimed_time='now').set_tip_to(alice, D('3.00'))
        self.make_participant('evelyn', claimed_time='now').set_tip_to(alice, D('4.00'))
        self.make_participant('francis', claimed_time='now').set_tip_to(alice, D('5.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee='alice' AND amount > 0")
        assert ntips() == 5
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0


    # cpi - clear_personal_information

    def test_cpi_clears_personal_information(self):
        alice = self.make_participant( 'alice'
                                     , statement='not forgetting to be awesome!'
                                     , goal=100
                                     , anonymous_giving=True
                                     , anonymous_receiving=True
                                     , number='plural'
                                     , avatar_url='img-url'
                                     , email=('alice@example.com', True)
                                     , claimed_time='now'
                                     , session_token='deadbeef'
                                     , session_expires='2000-01-01'
                                     , giving=20
                                     , pledging=30
                                     , receiving=40
                                     , npatrons=21
                                      )
        assert Participant.from_username('alice').number == 'plural' # sanity check

        with self.db.get_cursor() as cursor:
            alice.clear_personal_information(cursor)
        new_alice = Participant.from_username('alice')

        assert alice.statement == new_alice.statement == ''
        assert alice.goal == new_alice.goal == None
        assert (alice.anonymous_giving, new_alice.anonymous_giving) == (False, False)
        assert (alice.anonymous_receiving, new_alice.anonymous_giving) == (False, False)
        assert alice.number == new_alice.number == 'singular'
        assert alice.avatar_url == new_alice.avatar_url == None
        assert alice.email == new_alice.email == None
        assert alice.claimed_time == new_alice.claimed_time == None
        assert alice.giving == new_alice.giving == 0
        assert alice.pledging == new_alice.pledging == 0
        assert alice.receiving == new_alice.receiving == 0
        assert alice.npatrons == new_alice.npatrons == 0
        assert alice.session_token == new_alice.session_token == None
        assert alice.session_expires.year == new_alice.session_expires.year == date.today().year

    def test_cpi_clears_communities(self):
        alice = self.make_participant('alice')
        alice.insert_into_communities(True, 'test', 'test')
        bob = self.make_participant('bob')
        bob.insert_into_communities(True, 'test', 'test')

        assert Community.from_slug('test').nmembers == 2  # sanity check

        with self.db.get_cursor() as cursor:
            alice.clear_personal_information(cursor)

        assert Community.from_slug('test').nmembers == 1

    def test_cpi_clears_teams(self):
        team = self.make_participant('team', number='plural')
        alice = self.make_participant('alice', claimed_time='now')
        team.add_member(alice)
        bob = self.make_participant('bob', claimed_time='now')
        team.add_member(bob)

        assert len(team.get_current_takes()) == 2  # sanity check

        with self.db.get_cursor() as cursor:
            alice.clear_personal_information(cursor)

        assert len(team.get_current_takes()) == 1


    # uic = update_is_closed

    def test_uic_updates_is_closed(self):
        alice = self.make_participant('alice')
        alice.update_is_closed(True)

        assert alice.is_closed
        assert Participant.from_username('alice').is_closed

    def test_uic_updates_is_closed_False(self):
        alice = self.make_participant('alice')
        alice.update_is_closed(True)
        alice.update_is_closed(False)

        assert not alice.is_closed
        assert not Participant.from_username('alice').is_closed

    def test_uic_uses_supplied_cursor(self):
        alice = self.make_participant('alice')

        with self.db.get_cursor() as cursor:
            alice.update_is_closed(True, cursor)
            assert alice.is_closed
            assert not Participant.from_username('alice').is_closed
        assert Participant.from_username('alice').is_closed
