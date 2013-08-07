from __future__ import unicode_literals
import datetime
from decimal import Decimal

from aspen.utils import utcnow
from nose.tools import assert_raises, assert_equals

from gittip.models import Absorption, Tip
from gittip.participant import Participant, NeedConfirmation
from gittip.testing import Harness
from gittip.elsewhere.twitter import TwitterAccount

# TODO: Test that accounts elsewhere are not considered claimed by default


class StubAccount(object):
    def __init__(self, platform, user_id):
        self.platform = platform
        self.user_id = user_id


class TestNeedConfirmation(Harness):
    def test_need_confirmation1(self):
        assert not NeedConfirmation(False, False, False)

    def test_need_confirmation2(self):
        assert NeedConfirmation(False, False, True)

    def test_need_confirmation3(self):
        assert not NeedConfirmation(False, True, False)

    def test_need_confirmation4(self):
        assert NeedConfirmation(False, True, True)

    def test_need_confirmation5(self):
        assert NeedConfirmation(True, False, False)

    def test_need_confirmation6(self):
        assert NeedConfirmation(True, False, True)

    def test_need_confirmation7(self):
        assert NeedConfirmation(True, True, False)

    def test_need_confirmation8(self):
        assert NeedConfirmation(True, True, True)


class TestAbsorptions(Harness):
    # TODO: These tests should probably be moved to absorptions tests
    def setUp(self):
        super(Harness, self).setUp()
        now = utcnow()
        hour_ago = now - datetime.timedelta(hours=1)
        for username in ['alice', 'bob', 'carl']:
            self.make_participant(username, claimed_time=hour_ago,
                                  last_bill_result='')
        deadbeef = TwitterAccount('1', {'screen_name': 'deadbeef'})
        self.deadbeef_original_username = deadbeef.participant

        Participant('carl').set_tip_to('bob', '1.00')
        Participant('alice').set_tip_to(self.deadbeef_original_username, '1.00')
        Participant('bob').take_over(deadbeef, have_confirmation=True)

    def test_participant_can_be_instantiated(self):
        expected = Participant
        actual = Participant(None).__class__
        assert actual is expected, actual

    def test_bob_has_two_dollars_in_tips(self):
        expected = Decimal('2.00')
        actual = Participant('bob').get_dollars_receiving()
        assert_equals(actual, expected)

    def test_alice_gives_to_bob_now(self):
        expected = Decimal('1.00')
        actual = Participant('alice').get_tip_to('bob')
        assert_equals(actual, expected)

    def test_deadbeef_is_archived(self):
        actual = Absorption.query\
                           .filter_by(absorbed_by='bob',
                                      absorbed_was=self.deadbeef_original_username)\
                           .count()
        expected = 1
        assert_equals(actual, expected)

    def test_alice_doesnt_gives_to_deadbeef_anymore(self):
        expected = Decimal('0.00')
        actual = Participant('alice').get_tip_to(self.deadbeef_original_username)
        assert actual == expected, actual

    def test_alice_doesnt_give_to_whatever_deadbeef_was_archived_as_either(self):
        expected = Decimal('0.00')
        actual = Participant('alice').get_tip_to(self.deadbeef_original_username)
        assert actual == expected, actual

    def test_attempts_to_change_archived_deadbeef_fail(self):
        participant = Participant(self.deadbeef_original_username)
        with assert_raises(AssertionError):
            participant.change_username('zombeef')

    def test_there_is_no_more_deadbeef(self):
        actual = Participant('deadbeef').get_details()
        assert actual is None, actual


class TestParticipant(Harness):
    def setUp(self):
        super(Harness, self).setUp()
        now = utcnow()
        for idx, username in enumerate(['alice', 'bob', 'carl'], start=1):
            self.make_participant(username, claimed_time=now)
            twitter_account = TwitterAccount(idx, {'screen_name': username})
            Participant(username).take_over(twitter_account)

    def test_bob_is_singular(self):
        expected = True
        actual = Participant('bob').is_singular()
        assert_equals(actual, expected)

    def test_john_is_plural(self):
        expected = True
        self.make_participant('john', 'plural')
        actual = Participant('john').is_plural()
        assert_equals(actual, expected)

    def test_cant_take_over_claimed_participant_without_confirmation(self):
        bob_twitter = StubAccount('twitter', '2')
        with assert_raises(NeedConfirmation):
            Participant('alice').take_over(bob_twitter)

    def test_taking_over_yourself_sets_all_to_zero(self):
        bob_twitter = StubAccount('twitter', '2')
        Participant('alice').set_tip_to('bob', '1.00')
        Participant('alice').take_over(bob_twitter, have_confirmation=True)
        expected = Decimal('0.00')
        actual = Participant('alice').get_dollars_giving()
        assert_equals(actual, expected)

    def test_alice_ends_up_tipping_bob_two_dollars(self):
        carl_twitter = StubAccount('twitter', '3')
        Participant('alice').set_tip_to('bob', '1.00')
        Participant('alice').set_tip_to('carl', '1.00')
        Participant('bob').take_over(carl_twitter, have_confirmation=True)
        expected = Decimal('2.00')
        actual = Participant('alice').get_tip_to('bob')
        assert_equals(actual, expected)

    def test_bob_ends_up_tipping_alice_two_dollars(self):
        carl_twitter = StubAccount('twitter', '3')
        Participant('bob').set_tip_to('alice', '1.00')
        Participant('carl').set_tip_to('alice', '1.00')
        Participant('bob').take_over(carl_twitter, have_confirmation=True)
        expected = Decimal('2.00')
        actual = Participant('bob').get_tip_to('alice')
        assert_equals(actual, expected)

    def test_ctime_comes_from_the_older_tip(self):
        carl_twitter = StubAccount('twitter', '3')
        Participant('alice').set_tip_to('bob', '1.00')
        Participant('alice').set_tip_to('carl', '1.00')
        Participant('bob').take_over(carl_twitter, have_confirmation=True)

        tips = Tip.query.all()
        first, second = tips[0], tips[1]

        # sanity checks (these don't count :)
        assert len(tips) == 4
        assert first.tipper, first.tippee == ('alice', 'bob')
        assert second.tipper, second.tippee == ('alice', 'carl')

        expected = first.ctime
        actual = Tip.query.first().ctime
        assert_equals(actual, expected)

    def test_connecting_unknown_account_fails(self):
        unknown_account = StubAccount('github', 'jim')
        with assert_raises(AssertionError):
            Participant('bob').take_over(unknown_account)

