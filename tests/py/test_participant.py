import pytest

from liberapay.constants import (
    CURRENCIES, PAYPAL_CURRENCIES, USERNAME_SUFFIX_BLACKLIST,
)
from liberapay.exceptions import (
    BadAmount,
    InvalidId,
    NoSelfTipping,
    NoTippee,
    NonexistingElsewhere,
    UsernameAlreadyTaken,
    UsernameBeginsWithRestrictedCharacter,
    UsernameContainsInvalidCharacters,
    UsernameEndsWithForbiddenSuffix,
    UsernameIsEmpty,
    UsernameIsRestricted,
    UsernameTooLong,
)
from liberapay.i18n.currencies import Money
from liberapay.models.participant import NeedConfirmation, Participant
from liberapay.models.tip import Tip
from liberapay.testing import EUR, USD, Harness


class TestTakeOver(Harness):

    def test_empty_stub_is_deleted(self):
        alice = self.make_participant('alice')
        bob = self.make_elsewhere('twitter', 2, 'bob')
        alice.take_over(bob)
        r = self.db.one("DELETE FROM participants WHERE id = %s RETURNING id",
                        (bob.participant.id,))
        assert not r

    def test_cross_tip_doesnt_become_self_tip(self):
        alice = self.make_participant('alice', elsewhere='twitter')
        bob = self.make_elsewhere('twitter', 2, 'bob')
        alice.set_tip_to(bob.participant, EUR('1.00'))
        alice.take_over(bob, have_confirmation=True)
        self.db.self_check()

    def test_zero_cross_tip_doesnt_become_self_tip(self):
        alice = self.make_participant('alice')
        bob = self.make_elsewhere('twitter', 2, 'bob')
        alice.set_tip_to(bob.participant, EUR('1.00'))
        alice.set_tip_to(bob.participant, EUR('0.00'))
        alice.take_over(bob, have_confirmation=True)
        self.db.self_check()

    def test_do_not_take_over_stopped_tips_receiving(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        carl = self.make_elsewhere('twitter', 3, 'carl')
        bob.set_tip_to(carl, EUR('1.00'))
        bob.set_tip_to(carl, EUR('0.00'))
        alice.take_over(carl, have_confirmation=True)
        ntips = self.db.one("select count(*) from tips")
        assert 2 == ntips
        self.db.self_check()

    def test_consolidated_tips_receiving(self):
        alice = self.make_participant('alice')
        alice_card = self.upsert_route(alice, 'stripe-card')
        bob = self.make_participant('bob', elsewhere='twitter')
        carl = self.make_elsewhere('github', -1, 'carl')
        self.add_payment_account(bob, 'stripe')
        alice.set_tip_to(bob, EUR('1.00'))
        self.make_payin_and_transfer(alice_card, bob, EUR('10'))
        alice.set_tip_to(carl.participant, EUR('5.00'))
        bob.take_over(carl, have_confirmation=True)
        tips = self.db.all("select * from tips order by id asc")
        assert len(tips) == 4
        assert tips[2].tippee == bob.id
        assert tips[2].amount == EUR('5.00')
        assert tips[2].paid_in_advance == EUR('10')
        assert tips[2].is_funded is True
        assert tips[3].tippee == carl.participant.id
        assert tips[3].amount == EUR('5.00')
        assert tips[3].renewal_mode == 0
        assert tips[3].paid_in_advance is None
        assert tips[3].visibility == -1
        self.db.self_check()

    def test_idempotent(self):
        alice = self.make_participant('alice', elsewhere='twitter')
        bob = self.make_elsewhere('github', 2, 'bob')
        alice.take_over(bob, have_confirmation=True)
        alice.take_over(bob, have_confirmation=True)
        self.db.self_check()


class TestParticipant(Harness):

    def setUp(self):
        Harness.setUp(self)
        for username in ['alice', 'bob', 'carl']:
            p = self.make_participant(username, elsewhere='twitter')
            setattr(self, username, p)

    def test_comparison(self):
        assert self.alice == self.alice
        assert not (self.alice != self.alice)
        assert self.alice != self.bob
        assert not (self.alice == self.bob)
        assert self.alice != None
        assert not (self.alice == None)

    def test_cant_take_over_claimed_participant_without_confirmation(self):
        with self.assertRaises(NeedConfirmation):
            self.alice.take_over(('twitter', '', str(self.bob.id)))

    def test_connecting_unknown_account_fails(self):
        with self.assertRaises(Exception):
            self.bob.take_over(('github', '', 'jim'))

    def test_delete_elsewhere_nonexisting(self):
        with pytest.raises(NonexistingElsewhere):
            self.alice.delete_elsewhere('github', '', 1)

    def test_delete_elsewhere(self):
        g = self.make_elsewhere('github', 1, 'alice')
        alice = self.alice
        alice.take_over(g)
        # test preconditions
        accounts = alice.get_accounts_elsewhere()
        assert len(accounts) == 2
        assert set(a.platform for a in accounts) == {'github', 'twitter'}
        # do the thing
        alice.delete_elsewhere('twitter', '', alice.id)
        # check the result
        accounts = alice.get_accounts_elsewhere()
        assert len(accounts) == 1
        assert set(a.platform for a in accounts) == {'github'}


class TestStub(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.stub = self.make_stub()  # Our protagonist

    def test_changing_username_successfully(self):
        self.stub.change_username('user2')
        actual = Participant.from_username('user2')
        assert self.stub == actual

    def test_changing_username_to_nothing(self):
        with self.assertRaises(UsernameIsEmpty):
            self.stub.change_username('')

    def test_changing_username_returns_the_new_username(self):
        returned = self.stub.change_username('foo_bar-baz')
        assert returned == 'foo_bar-baz'

    def test_changing_username_to_too_long(self):
        with self.assertRaises(UsernameTooLong):
            self.stub.change_username('123456789012345678901234567890123')

    def test_changing_username_to_already_taken(self):
        self.make_participant('user2')
        with self.assertRaises(UsernameAlreadyTaken):
            self.stub.change_username('user2')

    def test_changing_username_to_already_taken_is_case_insensitive(self):
        self.make_participant('UsEr2')
        with self.assertRaises(UsernameAlreadyTaken):
            self.stub.change_username('uSeR2')

    def test_changing_username_to_invalid_characters(self):
        with self.assertRaises(UsernameContainsInvalidCharacters):
            self.stub.change_username("\u2603")  # Snowman

    def test_changing_username_to_restricted_name(self):
        for name in self.client.website.restricted_usernames:
            if name.startswith('%'):
                expected_exception = UsernameContainsInvalidCharacters
            elif not name[:1].isalnum():
                expected_exception = UsernameBeginsWithRestrictedCharacter
            elif name[name.rfind('.'):] in USERNAME_SUFFIX_BLACKLIST:
                expected_exception = UsernameEndsWithForbiddenSuffix
            else:
                expected_exception = UsernameIsRestricted
            with self.assertRaises(expected_exception):
                self.stub.change_username(name)

    def test_getting_tips_not_made(self):
        expected = EUR('0.00')
        user2 = self.make_participant('user2')
        actual = self.stub.get_tip_to(user2).amount
        assert actual == expected


class Tests(Harness):

    def test_known_user_is_known(self):
        alice = self.make_participant('alice')
        alice2 = Participant.from_username('alice')
        assert alice == alice2

    def test_username_is_case_insensitive(self):
        self.make_participant('AlIcE')
        actual = Participant.from_username('aLiCe').username
        assert actual == 'AlIcE'

    # from_id

    def test_bad_id(self):
        with self.assertRaises(InvalidId):
            Participant.from_id(1786541)

    def test_null_id(self):
        with self.assertRaises(InvalidId):
            Participant.from_id(None)

    def test_good_id(self):
        alice = self.make_participant('alice')
        alice2 = Participant.from_id(alice.id)
        assert alice == alice2

    # from_username

    def test_bad_username(self):
        p = Participant.from_username('deadbeef')
        assert not p

    # accepted_currencies_set

    def test_accepted_currencies_set(self):
        alice = self.make_participant(
            'alice', accepted_currencies=None, email='alice@liberapay.com',
        )
        assert alice.payment_providers == 0
        assert alice.accepted_currencies_set == CURRENCIES
        r = self.client.PxST(
            "/alice/edit/currencies", {
                "accepted_currencies:TRY": "yes",
                "main_currency": "TRY",
            }, auth_as=alice,
        )
        assert r.code == 302, r.text
        alice = alice.refetch()
        assert alice.accepted_currencies_set == {'TRY'}
        # Check that currency preferences are ignored when they're incompatible
        # with the connected payment accounts.
        assert 'TRY' not in PAYPAL_CURRENCIES
        self.add_payment_account(alice, 'paypal')
        alice = alice.refetch()
        assert alice.payment_providers == 2
        assert alice.accepted_currencies_set == PAYPAL_CURRENCIES

    # set_tip_to - stt

    def test_stt_sets_tip_to(self):
        alice = self.make_participant('alice')
        bob = self.make_stub()
        alice.set_tip_to(bob, EUR('1.00'))
        actual = alice.get_tip_to(bob).amount
        assert actual == EUR('1.00')

    def test_stt_works_for_pledges(self):
        alice = self.make_participant('alice')
        bob = self.make_stub()
        t = alice.set_tip_to(bob, EUR('10.00'))
        assert type(t) is Tip
        assert isinstance(t.amount, Money)
        assert t['amount'] == EUR(10)
        assert t['is_funded'] is False
        assert t['is_pledge'] is True

    def test_stt_works_for_donations(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        self.add_payment_account(bob, 'stripe')
        t = alice.set_tip_to(bob, EUR('1.00'))
        assert t['amount'] == 1
        assert t['is_funded'] is False
        assert t['is_pledge'] is False

    def test_stt_converts_monthly_and_yearly_amounts_correctly(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob', accepted_currencies='EUR,USD')

        t = alice.set_tip_to(bob, EUR('0.05'), 'monthly')
        assert t['amount'] == EUR('0.01')

        t = alice.set_tip_to(bob, USD('433.34'), 'monthly')
        assert t['amount'] == USD('100.00')

        t = alice.set_tip_to(bob, USD('0.52'), 'yearly')
        assert t['amount'] == USD('0.01')

        t = alice.set_tip_to(bob, EUR('5200.00'), 'yearly')
        assert t['amount'] == EUR('100.00')

    def test_stt_doesnt_allow_self_tipping(self):
        alice = self.make_participant('alice')
        with pytest.raises(NoSelfTipping):
            alice.set_tip_to(alice, EUR('10.00'))

    def test_stt_doesnt_allow_just_any_ole_amount(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')

        with self.assertRaises(BadAmount) as cm:
            alice.set_tip_to(bob, EUR('0.001'))
        expected = "'€0.00' is not a valid weekly donation amount (min=€0.01, max=€100.00)"
        actual = cm.exception.render_in_english()
        assert actual == expected

        with self.assertRaises(BadAmount) as cm:
            alice.set_tip_to(bob, USD('1000.00'))
        expected = "'$1,000.00' is not a valid weekly donation amount (min=$0.01, max=$100.00)"
        actual = cm.exception.render_in_english()
        assert actual == expected

        with self.assertRaises(BadAmount) as cm:
            alice.set_tip_to(bob, USD('0.01'), 'yearly')
        expected = "'$0.01' is not a valid yearly donation amount (min=$0.52, max=$5,200.00)"
        actual = cm.exception.render_in_english()
        assert actual == expected

        with self.assertRaises(BadAmount) as cm:
            alice.set_tip_to(bob, EUR('10000'), 'yearly')
        expected = "'€10,000.00' is not a valid yearly donation amount (min=€0.52, max=€5,200.00)"
        actual = cm.exception.render_in_english()
        assert actual == expected

    def test_stt_fails_to_tip_unknown_people(self):
        alice = self.make_participant('alice')
        with pytest.raises(NoTippee):
            alice.set_tip_to('bob', EUR('1.00'))

    # get_tips_awaiting_payment

    def test_get_tips_awaiting_payment(self):
        alice = self.make_participant('alice', email='alice@liberapay.com')
        bob = self.make_participant('bob', email='bob@liberapay.com')
        carl = self.make_participant('carl', email='carl@liberapay.com')
        team = self.make_participant('team', kind='group')
        team.add_member(carl)

        # 1st check: alice hasn't set up any donations yet
        groups, n_fundable = alice.get_tips_awaiting_payment()
        assert isinstance(groups, dict)
        assert n_fundable == 0
        for v in groups.values():
            assert v == []

        alice.set_tip_to(bob, EUR('1.00'))
        alice.set_tip_to(carl, EUR('1.01'))
        alice.set_tip_to(team, EUR('1.02'))

        # 2nd check: no payment accounts to send the donations to
        groups, n_fundable = alice.get_tips_awaiting_payment()
        assert n_fundable == 0
        assert not groups['fundable']
        assert len(groups['no_provider']) == 3

        self.add_payment_account(carl, 'stripe', country='FR')
        self.add_payment_account(carl, 'paypal', country='FR')

        # 3rd check: two fundable donations are grouped, the other one isn't fundable
        groups, n_fundable = alice.get_tips_awaiting_payment()
        assert n_fundable == 2
        assert len(groups['fundable']) == 1
        assert len(groups['fundable'][0]) == 2
        assert len(groups['no_provider']) == 1

        self.add_payment_account(bob, 'stripe', country='DE')

        # 4th check: all three donations are fundable and grouped into a single payment
        groups, n_fundable = alice.get_tips_awaiting_payment()
        assert n_fundable == 3
        assert len(groups['fundable']) == 1
        assert len(groups['fundable'][0]) == 3
        assert len(groups['no_provider']) == 0

        dana = self.make_participant('dana', email='dana@liberapay.com')
        self.add_payment_account(dana, 'paypal')
        alice.set_tip_to(dana, EUR('1.03'))

        # 5th check: a fourth donation has been added, it can't be grouped with the others
        groups, n_fundable = alice.get_tips_awaiting_payment()
        assert n_fundable == 4
        assert len(groups['fundable']) == 2
        assert len(groups['fundable'][0]) == 3

        r = self.client.PxST(
            "/bob/edit/currencies", {
                "accepted_currencies:USD": "yes",
                "main_currency": "USD",
            }, auth_as=bob,
        )
        assert r.code == 302, r.text

        # 6th check: one of the recipients no longer accepts the donation currency
        groups, n_fundable = alice.get_tips_awaiting_payment()
        assert n_fundable == 4
        assert len(groups['currency_conflict']) == 1
        assert len(groups['fundable']) == 2
        assert len(groups['fundable'][0]) == 2

    # giving, npatrons and receiving

    def test_only_funded_tips_count(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        dana = self.make_participant('dana')
        alice_card = self.upsert_route(alice, 'stripe-card')
        alice.set_tip_to(dana, EUR('3.00'))
        self.make_payin_and_transfer(alice_card, dana, EUR('15.00'))
        alice.set_tip_to(bob, EUR('6.00'))
        self.make_payin_and_transfer(alice_card, bob, EUR('30.00'))
        bob.set_tip_to(alice, EUR('5.00'))
        bob.set_tip_to(dana, EUR('2.00'))
        carl.set_tip_to(dana, EUR('2.08'))

        assert alice.giving == EUR('9.00')
        assert alice.receiving == EUR('0.00')
        assert bob.giving == EUR('0.00')
        assert bob.receiving == EUR('6.00')
        assert carl.giving == EUR('0.00')
        assert carl.receiving == EUR('0.00')
        assert dana.receiving == EUR('3.00')
        assert dana.npatrons == 1

        funded_tips = self.db.all("SELECT amount FROM tips WHERE is_funded ORDER BY id")
        assert funded_tips == [3, 6]

    def test_only_latest_tip_counts(self):
        alice = self.make_participant('alice')
        alice_card = self.upsert_route(alice, 'stripe-card')
        bob = self.make_participant('bob')
        bob_card = self.upsert_route(bob, 'stripe-card')
        carl = self.make_participant('carl')
        alice.set_tip_to(carl, EUR('12.00'))
        alice.set_tip_to(carl, EUR('3.00'))
        self.make_payin_and_transfer(alice_card, carl, EUR('30.00'))
        bob.set_tip_to(carl, EUR('2.00'))
        self.make_payin_and_transfer(bob_card, carl, EUR('20.00'))
        bob.set_tip_to(carl, EUR('0.00'))
        assert alice.giving == EUR('3.00')
        assert bob.giving == EUR('2.00')
        assert carl.receiving == EUR('5.00')
        assert carl.npatrons == 2

    def test_receiving_includes_taking(self):
        alice = self.make_participant('alice')
        alice_card = self.upsert_route(alice, 'stripe-card')
        bob = self.make_participant('bob', taking=EUR('42.00'))
        alice.set_tip_to(bob, EUR('3.00'))
        self.make_payin_and_transfer(alice_card, bob, EUR('30.00'))
        assert Participant.from_username('bob').receiving == bob.receiving == EUR('45.00')

    def test_receiving_is_zero_for_patrons(self):
        alice = self.make_participant('alice')
        alice_card = self.upsert_route(alice, 'stripe-card')
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'stripe')
        alice.set_tip_to(bob, EUR('3.00'))
        self.make_payin_and_transfer(alice_card, bob, EUR('12.00'))

        bob.update_goal(EUR('-1'))
        assert bob.receiving == 0
        assert bob.npatrons == 0
        alice = Participant.from_id(alice.id)
        assert alice.giving == 0

    # pledging

    def test_pledging_isnt_giving(self):
        alice = self.make_participant('alice')
        bob = self.make_elsewhere('github', 58946, 'bob').participant
        alice.set_tip_to(bob, EUR('3.00'))
        assert alice.giving == EUR('0.00')

    # get_age_in_seconds - gais

    def test_gais_gets_age_in_seconds(self):
        alice = self.make_participant('alice')
        actual = alice.get_age_in_seconds()
        assert 0 < actual < 1

    def test_gais_returns_negative_one_if_None(self):
        alice = self.make_stub()
        actual = alice.get_age_in_seconds()
        assert actual == -1

    # resolve_stub - rs

    def test_rs_returns_None_when_there_is_no_elsewhere(self):
        resolved = self.make_stub().resolve_stub()
        assert resolved is None, resolved

    def test_rs_returns_bitbucket_url_for_stub_from_bitbucket(self):
        unclaimed = self.make_elsewhere('bitbucket', '1234', 'alice')
        stub = Participant.from_username(unclaimed.participant.username)
        actual = stub.resolve_stub()
        assert actual == "/on/bitbucket/alice/"

    def test_rs_returns_github_url_for_stub_from_github(self):
        unclaimed = self.make_elsewhere('github', '1234', 'alice')
        stub = Participant.from_username(unclaimed.participant.username)
        actual = stub.resolve_stub()
        assert actual == "/on/github/alice/"

    def test_rs_returns_twitter_url_for_stub_from_twitter(self):
        unclaimed = self.make_elsewhere('twitter', '1234', 'alice')
        stub = Participant.from_username(unclaimed.participant.username)
        actual = stub.resolve_stub()
        assert actual == "/on/twitter/alice/"

    def test_rs_returns_openstreetmap_url_for_stub_from_openstreetmap(self):
        unclaimed = self.make_elsewhere('openstreetmap', '1', 'alice')
        stub = Participant.from_username(unclaimed.participant.username)
        actual = stub.resolve_stub()
        assert actual == "/on/openstreetmap/alice/"

        
