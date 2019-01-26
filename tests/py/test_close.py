import pytest

from liberapay.billing.payday import Payday
from liberapay.exceptions import UnableToDistributeBalance
from liberapay.models.community import Community
from liberapay.models.participant import Participant, clean_up_closed_accounts
from liberapay.testing import EUR
from liberapay.testing.mangopay import FakeTransfersHarness


class TestClosing(FakeTransfersHarness):

    # close

    def test_close_closes(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice', balance=EUR('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')

        alice.set_tip_to(bob, EUR('3.00'))
        carl.set_tip_to(alice, EUR('2.00'))

        team.add_member(alice)
        team.add_member(bob)
        assert len(team.get_current_takes()) == 2  # sanity check

        alice.close('downstream')

        assert carl.get_tip_to(alice)['amount'] == EUR(2)
        assert alice.balance == 0
        assert len(team.get_current_takes()) == 1

    def test_close_raises_for_unknown_disbursement_strategy(self):
        alice = self.make_participant('alice', balance=EUR('0.00'))
        with pytest.raises(alice.UnknownDisbursementStrategy):
            alice.close('cheese')

    def test_close_page_is_usually_available(self):
        alice = self.make_participant('alice')
        body = self.client.GET('/alice/settings/close', auth_as=alice).text
        assert '<h3>Username' in body

    def test_close_page_is_not_available_during_payday(self):
        Payday.start()
        alice = self.make_participant('alice')
        body = self.client.GET('/alice/settings/close', auth_as=alice).text
        assert 'Personal Information' not in body
        assert 'Try Again Later' in body

    def test_can_post_to_close_page(self):
        alice = self.make_participant('alice')
        response = self.client.PxST('/alice/settings/close', auth_as=alice)
        assert response.code == 302
        assert response.headers[b'Location'] == b'/alice/'

    def test_cant_post_to_close_page_during_payday(self):
        Payday.start()
        alice = self.make_participant('alice')
        body = self.client.POST('/alice/settings/close', auth_as=alice).text
        assert 'Try Again Later' in body


    # dbtd - distribute_balances_to_donees

    def test_dbtd_distributes_balance_as_final_gift(self):
        alice = self.make_participant('alice', balance=EUR('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, EUR('3.00'))
        alice.set_tip_to(carl, EUR('2.00'))
        alice.distribute_balances_to_donees()
        assert Participant.from_username('bob').balance == EUR('6.00')
        assert Participant.from_username('carl').balance == EUR('4.00')
        assert Participant.from_username('alice').balance == EUR('0.00')

    def test_dbtd_needs_claimed_tips(self):
        alice = self.make_participant('alice', balance=EUR('10.00'))
        bob = self.make_stub()
        carl = self.make_stub()
        alice.set_tip_to(bob, EUR('3.00'))
        alice.set_tip_to(carl, EUR('2.00'))
        with pytest.raises(UnableToDistributeBalance):
            alice.distribute_balances_to_donees()
        assert Participant.from_id(bob.id).balance == EUR('0.00')
        assert Participant.from_id(carl.id).balance == EUR('0.00')
        assert Participant.from_id(alice.id).balance == EUR('10.00')

    def test_dbtd_gives_all_to_claimed(self):
        alice = self.make_participant('alice', balance=EUR('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_stub()
        alice.set_tip_to(bob, EUR('3.00'))
        alice.set_tip_to(carl, EUR('2.00'))
        alice.distribute_balances_to_donees()
        assert Participant.from_id(bob.id).balance == EUR('10.00')
        assert Participant.from_id(carl.id).balance == EUR('0.00')
        assert Participant.from_id(alice.id).balance == EUR('0.00')

    def test_dbtd_skips_stopped_tips(self):
        alice = self.make_participant('alice', balance=EUR('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, EUR('1.00'))
        alice.stop_tip_to(bob)
        alice.set_tip_to(carl, EUR('2.00'))
        alice.distribute_balances_to_donees()
        assert Participant.from_username('bob').balance == EUR('0.00')
        assert Participant.from_username('carl').balance == EUR('10.00')
        assert Participant.from_username('alice').balance == EUR('0.00')

    def test_dbtd_favors_highest_tippee_in_rounding_errors(self):
        alice = self.make_participant('alice', balance=EUR('10.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, EUR('3.00'))
        alice.set_tip_to(carl, EUR('6.00'))
        alice.distribute_balances_to_donees()
        assert Participant.from_username('bob').balance == EUR('3.33')
        assert Participant.from_username('carl').balance == EUR('6.67')
        assert Participant.from_username('alice').balance == EUR('0.00')

    def test_dbtd_with_zero_balance_is_a_noop(self):
        alice = self.make_participant('alice', balance=EUR('0.00'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(bob, EUR('3.00'))
        alice.set_tip_to(carl, EUR('6.00'))
        alice.distribute_balances_to_donees()
        assert self.db.one("SELECT count(*) FROM tips") == 2
        assert Participant.from_username('bob').balance == EUR('0.00')
        assert Participant.from_username('carl').balance == EUR('0.00')
        assert Participant.from_username('alice').balance == EUR('0.00')

    def test_dbtd_distributes_to_team(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice', balance=EUR('0.01'))
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        alice.set_tip_to(team, EUR('3.00'))
        team.set_take_for(alice, EUR('1.00'), team)
        team.set_take_for(bob, EUR('1.00'), team)
        team.set_take_for(carl, EUR('0.01'), team)
        alice.distribute_balances_to_donees()
        assert alice.balance == 0
        assert bob.refetch().balance == EUR('0.01')
        assert carl.refetch().balance == 0

    def test_dbtd_distributes_to_team_of_one_with_zero_take(self):
        team = self.make_participant('team', kind='group')
        alice = self.make_participant('alice', balance=EUR('0.12'))
        bob = self.make_participant('bob')
        alice.set_tip_to(team, EUR('3.00'))
        team.add_member(bob)
        alice.distribute_balances_to_donees()
        assert alice.balance == 0
        assert bob.refetch().balance == EUR('0.12')


    # ctg - clear_tips_giving

    def test_ctg_clears_tips_giving(self):
        alice = self.make_participant('alice')
        alice.set_tip_to(self.make_participant('bob'), EUR('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tipper=%s AND renewal_mode > 0",
                                    (alice.id,))
        assert ntips() == 1
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0

    def test_ctg_doesnt_duplicate_zero_tips(self):
        alice = self.make_participant('alice')
        bob = self.make_stub()
        alice.set_tip_to(bob, EUR('1.00'))
        alice.set_tip_to(bob, EUR('0.00'))
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
        alice.set_tip_to(self.make_participant('bob'), EUR('1.00'))
        alice.set_tip_to(self.make_participant('carl'), EUR('1.00'))
        alice.set_tip_to(self.make_participant('darcy'), EUR('1.00'))
        alice.set_tip_to(self.make_participant('evelyn'), EUR('1.00'))
        alice.set_tip_to(self.make_participant('francis'), EUR('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tipper=%s AND renewal_mode > 0",
                                    (alice.id,))
        assert ntips() == 5
        with self.db.get_cursor() as cursor:
            alice.clear_tips_giving(cursor)
        assert ntips() == 0


    # ctr - clear_tips_receiving

    def test_ctr_clears_tips_receiving(self):
        alice = self.make_participant('alice')
        self.make_participant('bob').set_tip_to(alice, EUR('1.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee=%s AND renewal_mode > 0",
                                    (alice.id,))
        assert ntips() == 1
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0

    def test_ctr_doesnt_duplicate_stopped_tips(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        bob.set_tip_to(alice, EUR('1.00'))
        bob.set_tip_to(alice, EUR('0.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee=%s", (alice.id,))
        assert ntips() == 2
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 2

    def test_ctr_doesnt_insert_when_theres_no_tip(self):
        alice = self.make_participant('alice')
        ntips = lambda: self.db.one("SELECT count(*) FROM tips WHERE tippee=%s", (alice.id,))
        assert ntips() == 0
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0

    def test_ctr_clears_multiple_tips_receiving(self):
        alice = self.make_stub()
        self.make_participant('bob').set_tip_to(alice, EUR('1.00'))
        self.make_participant('carl').set_tip_to(alice, EUR('2.00'))
        self.make_participant('darcy').set_tip_to(alice, EUR('3.00'))
        self.make_participant('evelyn').set_tip_to(alice, EUR('4.00'))
        self.make_participant('francis').set_tip_to(alice, EUR('5.00'))
        ntips = lambda: self.db.one("SELECT count(*) FROM current_tips "
                                    "WHERE tippee=%s AND renewal_mode > 0",
                                    (alice.id,))
        assert ntips() == 5
        with self.db.get_cursor() as cursor:
            alice.clear_tips_receiving(cursor)
        assert ntips() == 0


    # epi - erase_personal_information

    def test_epi_deletes_personal_information(self):
        alice = self.make_participant(
            'alice',
            hide_giving=True,
            hide_receiving=True,
            avatar_url='img-url',
            email='alice@example.com',
        )
        alice.upsert_statement('en', 'not forgetting to be awesome!')
        alice.add_email('alice@example.net')

        alice.erase_personal_information()
        new_alice = Participant.from_username('alice')

        assert alice.get_statement(['en']) == (None, None)
        assert alice.hide_giving == new_alice.hide_giving == True
        assert alice.hide_receiving == new_alice.hide_receiving == True
        assert alice.avatar_url == new_alice.avatar_url == None
        assert alice.email == new_alice.email
        emails = alice.get_emails()
        assert len(emails) == 1
        assert emails[0].address == 'alice@example.com'
        assert emails[0].verified

    def test_epi_clears_communities(self):
        alice = self.make_participant('alice')
        c = alice.create_community('test')
        alice.upsert_community_membership(True, c.id)
        bob = self.make_participant('bob')
        bob.upsert_community_membership(True, c.id)

        assert Community.from_name('test').nmembers == 2  # sanity check

        alice.erase_personal_information()

        assert Community.from_name('test').nmembers == 1


    def test_clean_up_closed_accounts(self):
        alice = self.make_participant(
            'alice',
            goal=EUR(555),
            avatar_url='img-url',
            email='alice@example.com',
        )
        alice.upsert_statement('en', 'not forgetting to be awesome!')
        alice.add_email('alice@example.net')
        alice.close(None)

        cleaned = clean_up_closed_accounts()
        assert cleaned == 0

        self.db.run("UPDATE events SET ts = ts - interval '7 days'")
        cleaned = clean_up_closed_accounts()
        assert cleaned == 1

        alice = alice.refetch()
        assert alice.get_statement(['en']) == (None, None)
        assert alice.goal == EUR(-1)
        assert alice.avatar_url == None
        assert alice.email == 'alice@example.com'
        emails = alice.get_emails()
        assert len(emails) == 1
        assert emails[0].address == 'alice@example.com'
        assert emails[0].verified


    def test_reopening_closed_account(self):
        alice = self.make_participant(
            'alice',
            hide_giving=True,
            hide_receiving=True,
            avatar_url='img-url',
            email='alice@example.com',
        )
        alice.update_goal(EUR(100))
        alice.upsert_statement('en', 'not forgetting to be awesome!')
        alice.add_email('alice@example.net')

        alice.close(None)
        alice.update_status('active')
        new_alice = Participant.from_username('alice')

        assert alice.get_statement(['en']).content
        assert alice.goal == new_alice.goal == EUR(100)
        assert alice.hide_giving == new_alice.hide_giving == True
        assert alice.hide_receiving == new_alice.hide_receiving == True
        assert alice.avatar_url == new_alice.avatar_url == 'img-url'
        assert alice.email == new_alice.email
        emails = alice.get_emails()
        assert len(emails) == 2
