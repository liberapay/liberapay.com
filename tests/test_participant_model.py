from __future__ import unicode_literals
import random
import datetime
from decimal import Decimal

import psycopg2
import pytz
from nose.tools import assert_raises

from gittip.testing import Harness
from gittip.models import Participant, Tip
from gittip.participant import Participant as OldParticipant


class TestParticipant(Harness):

    def random_restricted_id(self):
        """ helper method that randomly chooses a restricted id for testing """
        from gittip import RESTRICTED_IDS
        random_item = random.choice(RESTRICTED_IDS)
        while random_item.startswith('%'):
            random_item = random.choice(RESTRICTED_IDS)
        return random_item

    def setUp(self):
        super(Harness, self).setUp()
        self.participant = Participant(id='user1') # Our protagonist
        self.session.add(self.participant)
        self.session.commit()


    def test_claiming_participant(self):
        expected = now = datetime.datetime.now(pytz.utc)
        self.participant.set_as_claimed(claimed_at=now)
        actual = self.participant.claimed_time
        assert actual == expected, actual

    def test_changing_id_successfully(self):
        self.participant.change_id('user2')
        actual = Participant.query.get('user2')
        assert self.participant == actual, actual

    def test_changing_id_to_too_long(self):
        with assert_raises(Participant.IdTooLong):
            self.participant.change_id('123456789012345678901234567890123')

    def test_changing_id_to_already_taken(self):
        self.session.add(Participant(id='user2'))
        self.session.commit()
        with assert_raises(Participant.IdAlreadyTaken):
            self.participant.change_id('user2')

    def test_changing_id_to_invalid_characters(self):
        with assert_raises(Participant.IdContainsInvalidCharacters):
            self.participant.change_id(u"\u2603") # Snowman

    def test_changing_id_to_restricted_name(self):
        with assert_raises(Participant.IdIsRestricted):
            self.participant.change_id(self.random_restricted_id())

    def test_getting_tips_actually_made(self):
        expected = Decimal('1.00')
        self.session.add(Participant(id='user2'))
        self.session.add(Tip(tipper='user1', tippee='user2', amount=expected,
                             ctime=datetime.datetime.now(pytz.utc)))
        self.session.commit()
        actual = self.participant.get_tip_to('user2')
        assert actual == expected, actual

    def test_getting_tips_not_made(self):
        expected = Decimal('0.00')
        self.session.add(Participant(id='user2'))
        self.session.commit()
        actual = self.participant.get_tip_to('user2')
        assert actual == expected, actual


    # set_tip_to - stt

    def test_stt_sets_tip_to(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')
        alice.set_tip_to('bob', '1.00')

        actual = alice.get_tip_to('bob')
        assert actual == Decimal('1.00'), actual

    def test_stt_returns_a_Decimal(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')
        actual = alice.set_tip_to('bob', '1.00')
        assert actual == Decimal('1.00'), actual

    def test_stt_doesnt_allow_self_tipping(self):
        alice = self.make_participant('alice', last_bill_result='')
        assert_raises( OldParticipant.NoSelfTipping
                     , alice.set_tip_to
                     , 'alice'
                     , '1000000.00'
                      )

    def test_stt_doesnt_allow_just_any_ole_amount(self):
        alice = self.make_participant('alice', last_bill_result='')
        self.make_participant('bob')
        assert_raises( OldParticipant.BadAmount
                     , alice.set_tip_to
                     , 'bob'
                     , '1000000.00'
                      )

    def test_stt_fails_to_tip_unknown_people(self):
        alice = self.make_participant('alice', last_bill_result='')
        assert_raises( psycopg2.IntegrityError
                     , alice.set_tip_to
                     , 'bob'
                     , '1.00'
                      )


    # get_dollars_receiving - gdr

    def test_gdr_only_sees_latest_tip(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '12.00')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('3.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual


    def test_gdr_includes_tips_from_accounts_with_a_working_card(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('3.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual

    def test_gdr_ignores_tips_from_accounts_with_no_card_on_file(self):
        alice = self.make_participant('alice', last_bill_result=None)
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('0.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual

    def test_gdr_ignores_tips_from_accounts_with_a_failing_card_on_file(self):
        alice = self.make_participant('alice', last_bill_result="Fail!")
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('0.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual


    def test_gdr_includes_tips_from_whitelisted_accounts(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , is_suspicious=False
                                      )
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('3.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual

    def test_gdr_includes_tips_from_unreviewed_accounts(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , is_suspicious=None
                                      )
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('3.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual

    def test_gdr_ignores_tips_from_blacklisted_accounts(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , is_suspicious=True
                                      )
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        expected = Decimal('0.00')
        actual = bob.get_dollars_receiving()
        assert actual == expected, actual


    # get_number_of_backers - gnob

    def test_gnob_gets_number_of_backers(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob', last_bill_result='')
        clancy = self.make_participant('clancy')

        alice.set_tip_to('clancy', '3.00')
        bob.set_tip_to('clancy', '1.00')

        self.session.commit()

        actual = clancy.get_number_of_backers()
        assert actual == 2, actual


    def test_gnob_includes_backers_with_a_working_card_on_file(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 1, actual

    def test_gnob_ignores_backers_with_no_card_on_file(self):
        alice = self.make_participant('alice', last_bill_result=None)
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 0, actual

    def test_gnob_ignores_backers_with_a_failing_card_on_file(self):
        alice = self.make_participant('alice', last_bill_result="Fail!")
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 0, actual


    def test_gnob_includes_whitelisted_backers(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , is_suspicious=False
                                      )
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 1, actual

    def test_gnob_includes_unreviewed_backers(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , is_suspicious=None
                                      )
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 1, actual

    def test_gnob_ignores_blacklisted_backers(self):
        alice = self.make_participant( 'alice'
                                     , last_bill_result=''
                                     , is_suspicious=True
                                      )
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '3.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 0, actual


    def test_gnob_ignores_backers_where_tip_is_zero(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob')
        alice.set_tip_to('bob', '0.00')
        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 0, actual

    def test_gnob_looks_at_latest_tip_only(self):
        alice = self.make_participant('alice', last_bill_result='')
        bob = self.make_participant('bob')

        alice.set_tip_to('bob', '1.00')
        alice.set_tip_to('bob', '12.00')
        alice.set_tip_to('bob', '3.00')
        alice.set_tip_to('bob', '6.00')
        alice.set_tip_to('bob', '0.00')

        self.session.commit()

        actual = bob.get_number_of_backers()
        assert actual == 0, actual


    # def get_details(self):
    # def resolve_unclaimed(self):
    # def set_as_claimed(self):
    # def change_id(self, suggested):
    # def get_accounts_elsewhere(self):
    # def get_tip_to(self, tippee):
    # def get_dollars_receiving(self):
    # def get_dollars_giving(self):
    # def get_chart_of_receiving(self):
    # def get_giving_for_profile(self, db=None):
    # def get_tips_and_total(self, for_payday=False, db=None):
    # def take_over(self, account_elsewhere, have_confirmation=False):
