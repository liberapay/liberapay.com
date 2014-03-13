from __future__ import absolute_import, division, print_function, unicode_literals

from decimal import Decimal as D
from datetime import datetime, timedelta

import balanced
import mock
from psycopg2 import IntegrityError

from aspen.utils import typecheck, utcnow
from gittip import billing
from gittip.billing.payday import Payday, skim_credit
from gittip.models.participant import Participant
from gittip.testing import Harness
from gittip.testing.balanced import BalancedHarness


class PaydayHarness(BalancedHarness):

    def setUp(self):
        BalancedHarness.setUp(self)
        self.payday = Payday(self.db)

    def fetch_payday(self):
        return self.db.one("SELECT * FROM paydays", back_as=dict)


class TestPaydayCharge(PaydayHarness):
    STRIPE_CUSTOMER_ID = 'cus_deadbeef'

    def get_numbers(self):
        """Return a list of 11 ints:

            nachs
            nach_failing
            nactive
            ncc_failing
            ncc_missing
            ncharges
            npachinko
            nparticipants
            ntippers
            ntips
            ntransfers

        """
        payday = self.fetch_payday()
        keys = [key for key in sorted(payday) if key.startswith('n')]
        return [payday[key] for key in keys]

    def test_charge_without_cc_details_returns_None(self):
        self.payday.start()
        actual = self.payday.charge(self.alice, D('1.00'))
        assert actual is None

    def test_charge_without_cc_marked_as_failure(self):
        self.payday.start()
        self.payday.charge(self.alice, D('1.00'))
        actual = self.get_numbers()
        assert actual == [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0]

    @mock.patch('gittip.billing.payday.Payday.charge_on_balanced')
    def test_charge_failure_returns_None(self, cob):
        cob.return_value = (D('10.00'), D('0.68'), 'FAILED')
        bob = self.make_participant('bob', last_bill_result="failure",
                                    balanced_customer_href=self.balanced_customer_href,
                                    stripe_customer_id=self.STRIPE_CUSTOMER_ID,
                                    is_suspicious=False)

        self.payday.start()
        actual = self.payday.charge(bob, D('1.00'))
        assert actual is None

    @mock.patch('gittip.billing.payday.Payday.charge_on_balanced')
    def test_charge_success_returns_None(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        bob = self.make_participant('bob', last_bill_result="failure",
                                    balanced_customer_href=self.balanced_customer_href,
                                    stripe_customer_id=self.STRIPE_CUSTOMER_ID,
                                    is_suspicious=False)

        self.payday.start()
        actual = self.payday.charge(bob, D('1.00'))
        assert actual is None

    @mock.patch('gittip.billing.payday.Payday.charge_on_balanced')
    def test_charge_success_updates_participant(self, cob):
        cob.return_value = (D('10.00'), D('0.68'), "")
        bob = self.make_participant('bob', last_bill_result="failure",
                                    balanced_customer_href=self.balanced_customer_href,
                                    is_suspicious=False)
        self.payday.start()
        self.payday.charge(bob, D('1.00'))

        bob = Participant.from_username('bob')
        expected = {'balance': D('9.32'), 'last_bill_result': ''}
        actual = {'balance': bob.balance,
                  'last_bill_result': bob.last_bill_result}
        assert actual == expected

    @mock.patch('gittip.billing.payday.Payday.charge_on_balanced')
    def test_payday_moves_money(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        day_ago = utcnow() - timedelta(days=1)
        bob = self.make_participant('bob', claimed_time=day_ago,
                                    last_bill_result='',
                                    is_suspicious=False)
        carl = self.make_participant('carl', claimed_time=day_ago,
                                     balanced_customer_href=self.balanced_customer_href,
                                     last_bill_result='',
                                     is_suspicious=False)
        carl.set_tip_to('bob', '6.00')  # under $10!
        self.payday.run()

        bob = Participant.from_username('bob')
        carl = Participant.from_username('carl')

        assert bob.balance == D('6.00')
        assert carl.balance == D('3.32')

    @mock.patch('gittip.billing.payday.Payday.charge_on_balanced')
    def test_payday_doesnt_move_money_from_a_suspicious_account(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        day_ago = utcnow() - timedelta(days=1)
        bob = self.make_participant('bob', claimed_time=day_ago,
                                    last_bill_result='',
                                    is_suspicious=False)
        carl = self.make_participant('carl', claimed_time=day_ago,
                                     balanced_customer_href=self.balanced_customer_href,
                                     last_bill_result='',
                                     is_suspicious=True)
        carl.set_tip_to('bob', '6.00')  # under $10!
        self.payday.run()

        bob = Participant.from_username('bob')
        carl = Participant.from_username('carl')

        assert bob.balance == D('0.00')
        assert carl.balance == D('0.00')

    @mock.patch('gittip.billing.payday.Payday.charge_on_balanced')
    def test_payday_doesnt_move_money_to_a_suspicious_account(self, charge_on_balanced):
        charge_on_balanced.return_value = (D('10.00'), D('0.68'), "")
        day_ago = utcnow() - timedelta(days=1)
        bob = self.make_participant('bob', claimed_time=day_ago,
                                    last_bill_result='',
                                    is_suspicious=True)
        carl = self.make_participant('carl', claimed_time=day_ago,
                                     balanced_customer_href=self.balanced_customer_href,
                                     last_bill_result='',
                                     is_suspicious=False)
        carl.set_tip_to('bob', '6.00')  # under $10!
        self.payday.run()

        bob = Participant.from_username('bob')
        carl = Participant.from_username('carl')

        assert bob.balance == D('0.00')
        assert carl.balance == D('0.00')

    def test_payday_moves_money_with_balanced(self):
        day_ago = utcnow() - timedelta(days=1)
        paying_customer = balanced.Customer().save()
        balanced.Card.fetch(self.card_href)\
                     .associate_to_customer(paying_customer)
        balanced.BankAccount.fetch(self.bank_account_href)\
                            .associate_to_customer(self.balanced_customer_href)
        bob = self.make_participant('bob', claimed_time=day_ago,
                                    balanced_customer_href=self.balanced_customer_href,
                                    last_bill_result='',
                                    is_suspicious=False)
        carl = self.make_participant('carl', claimed_time=day_ago,
                                     balanced_customer_href=paying_customer.href,
                                     last_bill_result='',
                                     is_suspicious=False)
        carl.set_tip_to('bob', '15.00')
        self.payday.run()

        bob = Participant.from_username('bob')
        carl = Participant.from_username('carl')

        assert bob.balance == D('0.00')
        assert carl.balance == D('0.00')

        bob_customer = balanced.Customer.fetch(bob.balanced_customer_href)
        carl_customer = balanced.Customer.fetch(carl.balanced_customer_href)

        bob_credits = bob_customer.credits.all()
        assert len(bob_credits) == 1
        assert bob_credits[0].amount == 1500
        assert bob_credits[0].description == 'bob'

        carl_debits = carl_customer.debits.all()
        assert len(carl_debits) == 1
        assert carl_debits[0].amount == 1576  # base amount + fee
        assert carl_debits[0].description == 'carl'


class TestPaydayChargeOnBalanced(PaydayHarness):

    def setUp(self):
        PaydayHarness.setUp(self)


    def test_charge_on_balanced(self):

        # XXX Why can't we do this in BalancedHarness.setUp? Understand VCR!
        balanced_customer_href = unicode(balanced.Customer().save().href)
        balanced.Card.fetch(self.card_href) \
                     .associate_to_customer(balanced_customer_href)

        actual = self.payday.charge_on_balanced( 'whatever username'
                                               , balanced_customer_href
                                               , D('10.00') # $10.00 USD
                                                )
        assert actual == (D('10.61'), D('0.61'), '')

    def test_charge_on_balanced_small_amount(self):

        # XXX Why can't we do this in BalancedHarness.setUp? Understand VCR!
        balanced_customer_href = unicode(balanced.Customer().save().href)
        balanced.Card.fetch(self.card_href) \
                     .associate_to_customer(balanced_customer_href)

        actual = self.payday.charge_on_balanced( 'whatever username'
                                               , balanced_customer_href
                                               , D('0.06')  # $0.06 USD
                                                )
        assert actual == (D('10.00'), D('0.59'), '')

    def test_charge_on_balanced_failure(self):
        customer_with_bad_card = unicode(balanced.Customer().save().href)
        card = balanced.Card(
            number='4444444444444448',
            expiration_year=2020,
            expiration_month=12
        ).save()
        card.associate_to_customer(customer_with_bad_card)

        actual = self.payday.charge_on_balanced( 'whatever username'
                                               , customer_with_bad_card
                                               , D('10.00')
                                                )
        assert actual == (D('10.61'), D('0.61'), '402 Client Error: PAYMENT REQUIRED')

    def test_charge_on_balanced_handles_MultipleFoundError(self):
        card = balanced.Card(
            number='4242424242424242',
            expiration_year=2020,
            expiration_month=12
        ).save()
        card.associate_to_customer(self.balanced_customer_href)

        card = balanced.Card(
            number='4242424242424242',
            expiration_year=2030,
            expiration_month=12
        ).save()
        card.associate_to_customer(self.balanced_customer_href)

        actual = self.payday.charge_on_balanced( 'whatever username'
                                               , self.balanced_customer_href
                                               , D('10.00')
                                                )
        assert actual == (D('10.61'), D('0.61'), 'MultipleResultsFound()')

    def test_charge_on_balanced_handles_NotFoundError(self):
        customer_with_no_card = unicode(balanced.Customer().save().href)
        actual = self.payday.charge_on_balanced( 'whatever username'
                                               , customer_with_no_card
                                               , D('10.00')
                                                )
        assert actual == (D('10.61'), D('0.61'), 'NoResultFound()')


class TestBillingCharges(PaydayHarness):
    BALANCED_CUSTOMER_HREF = '/customers/CU123123123'
    BALANCED_TOKEN = u'/cards/CU123123123'

    STRIPE_CUSTOMER_ID = u'cus_deadbeef'

    def test_mark_missing_funding(self):
        self.payday.start()
        before = self.fetch_payday()
        missing_count = before['ncc_missing']

        self.payday.mark_missing_funding()

        after = self.fetch_payday()
        assert after['ncc_missing'] == missing_count + 1

    def test_mark_charge_failed(self):
        self.payday.start()
        before = self.fetch_payday()
        fail_count = before['ncc_failing']

        with self.db.get_cursor() as cursor:
            self.payday.mark_charge_failed(cursor)

        after = self.fetch_payday()
        assert after['ncc_failing'] == fail_count + 1

    def test_mark_charge_success(self):
        self.payday.start()
        charge_amount, fee = 4, 2

        with self.db.get_cursor() as cursor:
            self.payday.mark_charge_success(cursor, charge_amount, fee)

        # verify paydays
        actual = self.fetch_payday()
        assert actual['ncharges'] == 1

    @mock.patch('stripe.Charge')
    def test_charge_on_stripe(self, ba):
        amount_to_charge = D('10.00')  # $10.00 USD
        expected_fee = D('0.61')
        charge_amount, fee, msg = self.payday.charge_on_stripe(
            self.alice.username, self.STRIPE_CUSTOMER_ID, amount_to_charge)

        assert charge_amount == amount_to_charge + fee
        assert fee == expected_fee
        assert ba.find.called_with(self.STRIPE_CUSTOMER_ID)
        customer = ba.find.return_value
        assert customer.debit.called_with( int(charge_amount * 100)
                                         , self.alice.username
                                          )


class TestPrepHit(PaydayHarness):

    ## XXX Consider turning _prep_hit in to a class method
    #@classmethod
    #def setUpClass(cls):
    #    PaydayHarness.setUpClass()
    #    cls.payday = Payday(mock.Mock())  # Mock out the DB connection

    def prep(self, amount):
        """Given a dollar amount as a string, return a 3-tuple.

        The return tuple is like the one returned from _prep_hit, but with the
        second value, a log message, removed.

        """
        typecheck(amount, unicode)
        out = list(self.payday._prep_hit(D(amount)))
        out = [out[0]] + out[2:]
        return tuple(out)

    def test_prep_hit_basically_works(self):
        actual = self.payday._prep_hit(D('20.00'))
        expected = (2091,
                    u'Charging %s 2091 cents ($20.00 + $0.91 fee = $20.91) on %s ' u'... ',
                    D('20.91'), D('0.91'))
        assert actual == expected

    def test_prep_hit_full_in_rounded_case(self):
        actual = self.payday._prep_hit(D('5.00'))
        expected = (1000,
                    u'Charging %s 1000 cents ($9.41 [rounded up from $5.00] + ' u'$0.59 fee = $10.00) on %s ... ',
                    D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_ten_dollars(self):
        actual = self.prep(u'10.00')
        expected = (1061, D('10.61'), D('0.61'))
        assert actual == expected

    def test_prep_hit_at_forty_cents(self):
        actual = self.prep(u'0.40')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_fifty_cents(self):
        actual = self.prep(u'0.50')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_sixty_cents(self):
        actual = self.prep(u'0.60')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_eighty_cents(self):
        actual = self.prep(u'0.80')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_fifteen(self):
        actual = self.prep(u'9.15')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_forty(self):
        actual = self.prep(u'9.40')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_forty_one(self):
        actual = self.prep(u'9.41')
        expected = (1000, D('10.00'), D('0.59'))
        assert actual == expected

    def test_prep_hit_at_nine_forty_two(self):
        actual = self.prep(u'9.42')
        expected = (1002, D('10.02'), D('0.60'))
        assert actual == expected


class TestBillingPayday(PaydayHarness):
    BALANCED_CUSTOMER_HREF = '/customers/CU123123123'

    def test_move_pending_to_balance_for_teams_does_so(self):
        self.make_participant('A', number='plural', balance=2, pending=3)
        self.payday.move_pending_to_balance_for_teams()
        actual = self.db.one("SELECT balance FROM participants WHERE username='A'")
        assert actual == 5

    def test_move_pending_to_balance_for_teams_ignores_new_teams(self):
        # See https://github.com/gittip/www.gittip.com/issues/1684
        self.make_participant('A', number='plural', balance=0, pending=None)
        self.payday.move_pending_to_balance_for_teams()
        actual = self.db.one("SELECT balance FROM participants WHERE username='A'")
        assert actual == 0

    @mock.patch('gittip.models.participant.Participant.get_tips_and_total')
    def test_charge_and_or_transfer_no_tips(self, get_tips_and_total):
        self.db.run("""

            UPDATE participants
               SET balance=1
                 , balanced_customer_href=%s
                 , is_suspicious=False
             WHERE username='alice'

        """, (self.BALANCED_CUSTOMER_HREF,))

        amount = D('1.00')

        ts_start = self.payday.start()

        tips, total = [], amount

        initial_payday = self.fetch_payday()
        self.payday.charge_and_or_transfer(ts_start, self.alice, tips, total)
        resulting_payday = self.fetch_payday()

        assert initial_payday['ntippers'] == resulting_payday['ntippers']
        assert initial_payday['ntips'] == resulting_payday['ntips']
        assert initial_payday['nparticipants'] + 1 == resulting_payday['nparticipants']

    @mock.patch('gittip.models.participant.Participant.get_tips_and_total')
    @mock.patch('gittip.billing.payday.Payday.tip')
    def test_charge_and_or_transfer(self, tip, get_tips_and_total):
        self.db.run("""

            UPDATE participants
               SET balance=1
                 , balanced_customer_href=%s
                 , is_suspicious=False
             WHERE username='alice'

        """, (self.BALANCED_CUSTOMER_HREF,))

        ts_start = self.payday.start()
        now = datetime.utcnow()
        amount = D('1.00')
        like_a_tip = {'amount': amount, 'tippee': 'mjallday', 'ctime': now,
                      'claimed_time': now}

        # success, success, claimed, failure
        tips = [like_a_tip, like_a_tip, like_a_tip, like_a_tip]
        total = amount

        ts_start = datetime.utcnow()

        return_values = [1, 1, 0, -1]
        return_values.reverse()

        def tip_return_values(*_):
            return return_values.pop()

        tip.side_effect = tip_return_values

        initial_payday = self.fetch_payday()
        self.payday.charge_and_or_transfer(ts_start, self.alice, tips, total)
        resulting_payday = self.fetch_payday()

        assert initial_payday['ntippers'] + 1 == resulting_payday['ntippers']
        assert initial_payday['ntips'] + 2 == resulting_payday['ntips']
        assert initial_payday['nparticipants'] + 1 == resulting_payday['nparticipants']

    @mock.patch('gittip.models.participant.Participant.get_tips_and_total')
    @mock.patch('gittip.billing.payday.Payday.charge')
    def test_charge_and_or_transfer_short(self, charge, get_tips_and_total):
        self.db.run("""

            UPDATE participants
               SET balance=1
                 , balanced_customer_href=%s
                 , is_suspicious=False
             WHERE username='alice'

        """, (self.BALANCED_CUSTOMER_HREF,))

        now = datetime.utcnow()
        amount = D('1.00')
        like_a_tip = {'amount': amount, 'tippee': 'mjallday', 'ctime': now,
                      'claimed_time': now}

        # success, success, claimed, failure
        tips = [like_a_tip, like_a_tip, like_a_tip, like_a_tip]
        get_tips_and_total.return_value = tips, amount

        ts_start = datetime.utcnow()

        # In real-life we wouldn't be able to catch an error as the charge
        # method will swallow any errors and return false. We don't handle this
        # return value within charge_and_or_transfer but instead continue on
        # trying to use the remaining credit in the user's account to payout as
        # many tips as possible.
        #
        # Here we're hacking the system and throwing the exception so execution
        # stops since we're only testing this part of the method. That smells
        # like we need to refactor.

        charge.side_effect = Exception()
        with self.assertRaises(Exception):
            billing.charge_and_or_transfer(ts_start, self.alice)
        assert charge.called_with(self.alice.username,
                                  self.BALANCED_CUSTOMER_HREF,
                                  amount)

    @mock.patch('gittip.billing.payday.Payday.transfer')
    @mock.patch('gittip.billing.payday.log')
    def test_tip(self, log, transfer):
        self.db.run("""

            UPDATE participants
               SET balance=1
                 , balanced_customer_href=%s
                 , is_suspicious=False
             WHERE username='alice'

        """, (self.BALANCED_CUSTOMER_HREF,))
        amount = D('1.00')
        invalid_amount = D('0.00')
        tip = { 'amount': amount
              , 'tippee': self.alice.username
              , 'claimed_time': utcnow()
               }
        ts_start = utcnow()

        result = self.payday.tip(self.alice, tip, ts_start)
        assert result == 1
        result = transfer.called_with(self.alice.username, tip['tippee'],
                                      tip['amount'])
        assert result

        assert log.called_with('SUCCESS: $1 from mjallday to alice.')

        # XXX: Should these tests be broken down to a separate class with the
        # common setup factored in to a setUp method.

        # XXX: We should have constants to compare the values to
        # invalid amount
        tip['amount'] = invalid_amount
        result = self.payday.tip(self.alice, tip, ts_start)
        assert result == 0

        tip['amount'] = amount

        # XXX: We should have constants to compare the values to
        # not claimed
        tip['claimed_time'] = None
        result = self.payday.tip(self.alice, tip, ts_start)
        assert result == 0

        # XXX: We should have constants to compare the values to
        # claimed after payday
        tip['claimed_time'] = utcnow()
        result = self.payday.tip(self.alice, tip, ts_start)
        assert result == 0

        ts_start = utcnow()

        # XXX: We should have constants to compare the values to
        # transfer failed
        transfer.return_value = False
        result = self.payday.tip(self.alice, tip, ts_start)
        assert result == -1

    @mock.patch('gittip.billing.payday.log')
    def test_start_zero_out_and_get_participants(self, log):
        self.make_participant('bob', balance=10, claimed_time=None,
                              pending=1,
                              balanced_customer_href=self.BALANCED_CUSTOMER_HREF)
        self.make_participant('carl', balance=10, claimed_time=utcnow(),
                              pending=1,
                              balanced_customer_href=self.BALANCED_CUSTOMER_HREF)
        self.db.run("""

            UPDATE participants
               SET balance=0
                 , claimed_time=null
                 , pending=null
                 , balanced_customer_href=%s
             WHERE username='alice'

        """, (self.BALANCED_CUSTOMER_HREF,))

        ts_start = self.payday.start()

        self.payday.zero_out_pending(ts_start)
        participants = self.payday.get_participants(ts_start)

        expected_logging_call_args = [
            ('Starting a new payday.'),
            ('Payday started at {}.'.format(ts_start)),
            ('Zeroed out the pending column.'),
            ('Fetched participants.'),
        ]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            assert args[0] == expected_logging_call_args.pop()

        log.reset_mock()

        # run a second time, we should see it pick up the existing payday
        second_ts_start = self.payday.start()
        self.payday.zero_out_pending(second_ts_start)
        second_participants = self.payday.get_participants(second_ts_start)

        assert ts_start == second_ts_start
        participants = list(participants)
        second_participants = list(second_participants)

        # carl is the only valid participant as he has a claimed time
        assert len(participants) == 1
        assert participants == second_participants

        expected_logging_call_args = [
            ('Picking up with an existing payday.'),
            ('Payday started at {}.'.format(second_ts_start)),
            ('Zeroed out the pending column.'),
            ('Fetched participants.')]
        expected_logging_call_args.reverse()
        for args, _ in log.call_args_list:
            assert args[0] == expected_logging_call_args.pop()

    @mock.patch('gittip.billing.payday.log')
    def test_end(self, log):
        self.payday.start()
        self.payday.end()
        assert log.called_with('Finished payday.')

        # finishing the payday will set the ts_end date on this payday record
        # to now, so this will not return any result
        result = self.db.one("SELECT count(*) FROM paydays "
                             "WHERE ts_end > '1970-01-01'")
        assert result == 1

    @mock.patch('gittip.billing.payday.log')
    @mock.patch('gittip.billing.payday.Payday.start')
    @mock.patch('gittip.billing.payday.Payday.payin')
    @mock.patch('gittip.billing.payday.Payday.end')
    def test_payday(self, end, payin, init, log):
        ts_start = utcnow()
        init.return_value = (ts_start,)
        greeting = 'Greetings, program! It\'s PAYDAY!!!!'

        self.payday.run()

        assert log.called_with(greeting)
        assert init.call_count
        assert payin.called_with(init.return_value)
        assert end.call_count


class TestBillingTransfer(PaydayHarness):
    def setUp(self):
        PaydayHarness.setUp(self)
        self.payday.start()
        self.tipper = self.make_participant('lgtest')
        #self.balanced_customer_href = '/v1/marketplaces/M123/accounts/A123'

    def test_transfer(self):
        amount = D('1.00')
        sender = self.make_participant('test_transfer_sender', pending=0,
                                       balance=1)
        recipient = self.make_participant('test_transfer_recipient', pending=0,
                                          balance=1)

        result = self.payday.transfer( sender.username
                                     , recipient.username
                                     , amount
                                      )
        assert result == True

        # no balance remaining for a second transfer
        result = self.payday.transfer( sender.username
                                     , recipient.username
                                     , amount
                                      )
        assert result == False

    def test_debit_participant(self):
        amount = D('1.00')
        subject = self.make_participant('test_debit_participant', pending=0,
                                        balance=1)

        initial_amount = subject.balance

        with self.db.get_cursor() as cursor:
            self.payday.debit_participant(cursor, subject.username, amount)

        subject = Participant.from_username('test_debit_participant')

        expected = initial_amount - amount
        actual = subject.balance
        assert actual == expected

        # this will fail because not enough balance
        with self.db.get_cursor() as cursor:
            with self.assertRaises(IntegrityError):
                self.payday.debit_participant(cursor, subject.username, amount)

    def test_skim_credit(self):
        actual = skim_credit(D('10.00'))
        assert actual == (D('10.00'), D('0.00'))

    def test_credit_participant(self):
        amount = D('1.00')
        subject = self.make_participant('test_credit_participant', pending=0,
                                        balance=1)

        initial_amount = subject.pending

        with self.db.get_cursor() as cursor:
            self.payday.credit_participant(cursor, subject.username, amount)

        subject = Participant.from_username('test_credit_participant') # reload

        expected = initial_amount + amount
        actual = subject.pending
        assert actual == expected

    def test_record_transfer(self):
        amount = D('1.00')
        subjects = ['jim', 'kate', 'bob']

        for subject in subjects:
            self.make_participant(subject, balance=1, pending=0)

        with self.db.get_cursor() as cursor:
            # Tip 'jim' twice
            for recipient in ['jim'] + subjects:
                self.payday.record_transfer( cursor
                                           , self.tipper.username
                                           , recipient
                                           , amount
                                            )

        for subject in subjects:
            # 'jim' is tipped twice
            expected = amount * 2 if subject == 'jim' else amount
            actual = self.db.one( "SELECT sum(amount) FROM transfers "
                                  "WHERE tippee=%s"
                                , (subject,)
                                 )
            assert actual == expected

    def test_record_transfer_invalid_participant(self):
        amount = D('1.00')

        with self.db.get_cursor() as cursor:
            with self.assertRaises(IntegrityError):
                self.payday.record_transfer( cursor
                                           , 'idontexist'
                                           , 'nori'
                                           , amount
                                            )

    def test_mark_transfer(self):
        amount = D('1.00')

        # Forces a load with current state in dict
        before_transfer = self.fetch_payday()

        with self.db.get_cursor() as cursor:
            self.payday.mark_transfer(cursor, amount)

        # Forces a load with current state in dict
        after_transfer = self.fetch_payday()

        expected = before_transfer['ntransfers'] + 1
        actual = after_transfer['ntransfers']
        assert actual == expected

        expected = before_transfer['transfer_volume'] + amount
        actual = after_transfer['transfer_volume']
        assert actual == expected

    def test_record_credit_updates_balance(self):
        self.payday.record_credit( amount=D("-1.00")
                                 , fee=D("0.41")
                                 , error=""
                                 , username="alice"
                                  )
        alice = Participant.from_username('alice')
        assert alice.balance == D("0.59")

    def test_record_credit_doesnt_update_balance_if_error(self):
        self.payday.record_credit( amount=D("-1.00")
                                 , fee=D("0.41")
                                 , error="SOME ERROR"
                                 , username="alice"
                                  )
        alice = Participant.from_username('alice')
        assert alice.balance == D("0.00")


class TestPachinko(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.payday = Payday(self.db)

    def test_get_participants_gets_participants(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20)
        a_team.add_member(self.make_participant('alice', claimed_time='now'))
        a_team.add_member(self.make_participant('bob', claimed_time='now'))

        ts_start = self.payday.start()

        actual = [p.username for p in self.payday.get_participants(ts_start)]
        expected = ['a_team', 'alice', 'bob']
        assert actual == expected

    def test_pachinko_pachinkos(self):
        a_team = self.make_participant('a_team', claimed_time='now', number='plural', balance=20, pending=0)
        a_team.add_member(self.make_participant('alice', claimed_time='now', balance=0, pending=0))
        a_team.add_member(self.make_participant('bob', claimed_time='now', balance=0, pending=0))

        ts_start = self.payday.start()

        participants = self.payday.genparticipants(ts_start, ts_start)
        self.payday.pachinko(ts_start, participants)
