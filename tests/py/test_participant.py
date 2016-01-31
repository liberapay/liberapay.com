from __future__ import print_function, unicode_literals

from decimal import Decimal

from six.moves.http_cookies import SimpleCookie

import pytest

import liberapay
from liberapay.constants import SESSION, SESSION_REFRESH
from liberapay.exceptions import (
    BadAmount,
    NoSelfTipping,
    NoTippee,
    NonexistingElsewhere,
    ProblemChangingUsername,
    UserDoesntAcceptTips,
    UsernameAlreadyTaken,
    UsernameContainsInvalidCharacters,
    UsernameIsEmpty,
    UsernameTooLong,
)
from liberapay.models.participant import NeedConfirmation, Participant
from liberapay.testing import Harness


class TestNeedConfirmation(Harness):
    def test_need_confirmation1(self):
        assert not NeedConfirmation(False, False)

    def test_need_confirmation2(self):
        assert NeedConfirmation(False, True)

    def test_need_confirmation3(self):
        assert NeedConfirmation(True, False)

    def test_need_confirmation4(self):
        assert NeedConfirmation(True, True)


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
        alice.set_tip_to(bob.participant, '1.00')
        alice.take_over(bob, have_confirmation=True)
        self.db.self_check()

    def test_zero_cross_tip_doesnt_become_self_tip(self):
        alice = self.make_participant('alice')
        bob = self.make_elsewhere('twitter', 2, 'bob')
        alice.set_tip_to(bob.participant, '1.00')
        alice.set_tip_to(bob.participant, '0.00')
        alice.take_over(bob, have_confirmation=True)
        self.db.self_check()

    def test_do_not_take_over_zero_tips_receiving(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        carl = self.make_elsewhere('twitter', 3, 'carl')
        bob.set_tip_to(carl, '1.00')
        bob.set_tip_to(carl, '0.00')
        alice.take_over(carl, have_confirmation=True)
        ntips = self.db.one("select count(*) from tips")
        assert 2 == ntips
        self.db.self_check()

    def test_consolidated_tips_receiving(self):
        alice = self.make_participant('alice', balance=1)
        bob = self.make_participant('bob', elsewhere='twitter')
        carl = self.make_elsewhere('github', -1, 'carl')
        alice.set_tip_to(bob, '1.00')  # funded
        alice.set_tip_to(carl.participant, '5.00')  # not funded
        bob.take_over(carl, have_confirmation=True)
        tips = self.db.all("select * from tips where amount > 0 order by id asc")
        assert len(tips) == 3
        assert tips[-1].amount == 6
        assert tips[-1].is_funded is False
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
            self.alice.take_over(('twitter', str(self.bob.id)))

    def test_connecting_unknown_account_fails(self):
        with self.assertRaises(Exception):
            self.bob.take_over(('github', 'jim'))

    def test_delete_elsewhere_nonexisting(self):
        with pytest.raises(NonexistingElsewhere):
            self.alice.delete_elsewhere('github', 1)

    def test_delete_elsewhere(self):
        g = self.make_elsewhere('github', 1, 'alice')
        alice = self.alice
        alice.take_over(g)
        # test preconditions
        accounts = alice.get_accounts_elsewhere()
        assert accounts['twitter'] and accounts['github']
        # do the thing
        alice.delete_elsewhere('twitter', alice.id)
        # unit test
        accounts = alice.get_accounts_elsewhere()
        assert accounts.get('twitter') is None and accounts['github']


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

    def test_changing_username_to_all_spaces(self):
        with self.assertRaises(UsernameIsEmpty):
            self.stub.change_username('    ')

    def test_changing_username_strips_spaces(self):
        self.stub.change_username('  aaa  ')
        actual = Participant.from_username('aaa')
        assert self.stub == actual

    def test_changing_username_returns_the_new_username(self):
        returned = self.stub.change_username('  foo_bar-baz  ')
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
            self.stub.change_username("\u2603") # Snowman

    def test_changing_username_to_restricted_name(self):
        from liberapay import RESTRICTED_USERNAMES
        for name in RESTRICTED_USERNAMES:
            with self.assertRaises(ProblemChangingUsername):
                self.stub.change_username(name)

    def test_getting_tips_not_made(self):
        expected = Decimal('0.00')
        user2 = self.make_participant('user2')
        actual = self.stub.get_tip_to(user2)['amount']
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

    # sessions

    def test_session_cookie_is_secure_if_it_should_be(self):
        canonical_scheme = liberapay.canonical_scheme
        liberapay.canonical_scheme = 'https'
        try:
            cookies = SimpleCookie()
            alice = self.make_participant('alice')
            alice.authenticated = True
            alice.sign_in(cookies)
            assert '; secure' in cookies[SESSION].output()
        finally:
            liberapay.canonical_scheme = canonical_scheme

    def test_session_is_regularly_refreshed(self):
        alice = self.make_participant('alice')
        alice.authenticated = True
        alice.sign_in(SimpleCookie())
        cookies = SimpleCookie()
        alice.keep_signed_in(cookies)
        assert SESSION not in cookies
        cookies = SimpleCookie()
        expires = alice.session_expires
        alice.set_session_expires(expires - SESSION_REFRESH)
        alice.keep_signed_in(cookies)
        assert SESSION in cookies

    # from_id

    def test_bad_id(self):
        p = Participant.from_id(1786541)
        assert not p

    def test_null_id(self):
        p = Participant.from_id(None)
        assert not p

    def test_good_id(self):
        alice = self.make_participant('alice')
        alice2 = Participant.from_id(alice.id)
        assert alice == alice2

    # from_username

    def test_bad_username(self):
        p = Participant.from_username('deadbeef')
        assert not p

    # id

    # set_tip_to - stt

    def test_stt_sets_tip_to(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_stub()
        alice.set_tip_to(bob, '1.00')

        actual = alice.get_tip_to(bob)['amount']
        assert actual == Decimal('1.00')

    def test_stt_works_for_pledges(self):
        alice = self.make_participant('alice', balance=1)
        bob = self.make_stub()
        t = alice.set_tip_to(bob, '10.00')
        assert isinstance(t, dict)
        assert isinstance(t['amount'], Decimal)
        assert t['amount'] == 10
        assert t['is_funded'] is False
        assert t['is_pledge'] is True
        assert t['first_time_tipper'] is True

    def test_stt_works_for_donations(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')
        t = alice.set_tip_to(bob, '1.00')
        assert t['amount'] == 1
        assert t['is_funded'] is True
        assert t['is_pledge'] is False
        assert t['first_time_tipper'] is True

    def test_stt_returns_False_for_second_time_tipper(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, '1.00')
        actual = alice.set_tip_to(bob, '2.00')
        assert actual['amount'] == 2
        assert actual['first_time_tipper'] is False

    def test_stt_doesnt_allow_self_tipping(self):
        alice = self.make_participant('alice', balance=100)
        with pytest.raises(NoSelfTipping):
            alice.set_tip_to(alice, '10.00')

    def test_stt_doesnt_allow_just_any_ole_amount(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')
        with pytest.raises(BadAmount):
            alice.set_tip_to(bob, '1000.00')

    def test_stt_fails_to_tip_unknown_people(self):
        alice = self.make_participant('alice', balance=100)
        with pytest.raises(NoTippee):
            alice.set_tip_to('bob', '1.00')

    # giving, npatrons and receiving

    def test_only_funded_tips_count(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')
        carl = self.make_participant('carl', last_bill_result="Fail!")
        dana = self.make_participant('dana')
        alice.set_tip_to(dana, '3.00')
        alice.set_tip_to(bob, '6.00')
        bob.set_tip_to(alice, '5.00')
        bob.set_tip_to(dana, '2.00')
        carl.set_tip_to(dana, '2.08')

        assert alice.giving == Decimal('9.00')
        assert alice.receiving == Decimal('5.00')
        assert bob.giving == Decimal('5.00')
        assert bob.receiving == Decimal('6.00')
        assert carl.giving == Decimal('0.00')
        assert carl.receiving == Decimal('0.00')
        assert dana.receiving == Decimal('3.00')
        assert dana.npatrons == 1

        funded_tips = self.db.all("SELECT amount FROM tips WHERE is_funded ORDER BY id")
        assert funded_tips == [3, 6, 5]

    def test_only_latest_tip_counts(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob', balance=100)
        carl = self.make_participant('carl')
        alice.set_tip_to(carl, '12.00')
        alice.set_tip_to(carl, '3.00')
        bob.set_tip_to(carl, '2.00')
        bob.set_tip_to(carl, '0.00')
        assert alice.giving == Decimal('3.00')
        assert bob.giving == Decimal('0.00')
        assert carl.receiving == Decimal('3.00')
        assert carl.npatrons == 1

    def test_receiving_includes_tips_from_whitelisted_accounts(self):
        alice = self.make_participant( 'alice'
                                     , balance=100
                                     , is_suspicious=False
                                      )
        bob = self.make_stub()
        alice.set_tip_to(bob, '3.00')

        assert bob.receiving == Decimal('3.00')
        assert bob.npatrons == 1

    def test_receiving_includes_tips_from_unreviewed_accounts(self):
        alice = self.make_participant( 'alice'
                                     , balance=100
                                     , is_suspicious=None
                                      )
        bob = self.make_stub()
        alice.set_tip_to(bob, '3.00')

        assert bob.receiving == Decimal('3.00')
        assert bob.npatrons == 1

    def test_receiving_ignores_tips_from_blacklisted_accounts(self):
        alice = self.make_participant( 'alice'
                                     , balance=100
                                     , is_suspicious=True
                                      )
        bob = self.make_stub()
        alice.set_tip_to(bob, '3.00')

        assert bob.receiving == Decimal('0.00')
        assert bob.npatrons == 0

    def test_receiving_includes_taking_when_updated_from_set_tip_to(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob', taking=Decimal('42.00'))
        alice.set_tip_to(bob, '3.00')
        assert Participant.from_username('bob').receiving == bob.receiving == Decimal('45.00')

    def test_receiving_is_zero_for_patrons(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, '3.00')

        bob.update_goal(Decimal('-1'))
        assert bob.receiving == 0
        assert bob.npatrons == 0
        alice = Participant.from_id(alice.id)
        assert alice.giving == 0

    # pledging

    def test_cant_pledge_to_locked_accounts(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_stub(goal=-1)
        with self.assertRaises(UserDoesntAcceptTips):
            alice.set_tip_to(bob, '3.00')

    def test_pledging_isnt_giving(self):
        alice = self.make_participant('alice', balance=100)
        bob = self.make_elsewhere('github', 58946, 'bob').participant
        alice.set_tip_to(bob, '3.00')
        assert alice.giving == Decimal('0.00')

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

    # suggested_payment

    def test_suggested_payment_is_zero_for_new_user(self):
        alice = self.make_participant('alice')
        assert alice.suggested_payment == 0
