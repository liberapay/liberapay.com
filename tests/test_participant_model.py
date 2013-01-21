import random
import datetime
from decimal import Decimal

import pytz
from nose.tools import assert_raises

from gittip.testing import BaseTestCase
from gittip.models import Participant, Tip

class ParticipantTestCase(BaseTestCase):
    def random_restricted_id(self):
        """ helper method that randomly chooses a restricted id for testing """
        from gittip import RESTRICTED_IDS
        random_item = random.choice(RESTRICTED_IDS)
        while random_item.startswith('%'):
            random_item = random.choice(RESTRICTED_IDS)
        return random_item

    def setUp(self):
        super(ParticipantTestCase, self).setUp()
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

    # TODO: Test that tips transfer
    def test_tips_being_received(self):
        amount = Decimal('2.00')
        self.session.add(Participant(id='user2'))
        self.session.add(Participant(id='user3'))
        for _ in xrange(3):
            self.session.add(Tip(tipper='user2', tippee='user1', amount=amount,
                                 ctime=datetime.datetime.now(pytz.utc)))
            self.session.add(Tip(tipper='user3', tippee='user1', amount=amount,
                                 ctime=datetime.datetime.now(pytz.utc)))
        expected = amount * 2
        actual = self.participant.dollars_receiving
        assert actual == expected, actual

    def test_tips_being_given(self):
        amount = Decimal('3.00')
        for tippee in ['user2', 'user3']:
            self.session.add(Participant(id=tippee))
            for _ in xrange(3):
                self.session.add(Tip(tipper='user1', tippee=tippee,
                                     amount=amount,
                                     ctime=datetime.datetime.now(pytz.utc)))
        expected = amount * 2
        actual = self.participant.dollars_giving
        assert actual == expected, actual

    def test_number_of_backers(self):
        expected = 2
        for backer in ['user2', 'user3']:
            self.session.add(Participant(id=backer, last_bill_result=''))
            self.session.add(Tip(tipper=backer, tippee='user1',
                                 amount=Decimal('1.0'),
                                 ctime=datetime.datetime.now(pytz.utc)))
        self.session.commit()
        actual = self.participant.get_number_of_backers()
        assert actual == expected, actual

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
