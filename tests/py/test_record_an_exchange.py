from __future__ import unicode_literals
from decimal import Decimal

from aspen.utils import utcnow
from gratipay.testing import Harness


class TestRecordAnExchange(Harness):

    # fixture
    # =======

    def make_participants(self):
        now = utcnow()
        self.make_participant('alice', claimed_time=now, is_admin=True)
        self.make_participant('bob', claimed_time=now)

    def record_an_exchange(self, amount, fee, note, status='succeeded', make_participants=True):
        if make_participants:
            self.make_participants()
        data = {'amount': amount, 'fee': fee, 'note': note}
        if status is not None:
            data['status'] = status
        return self.client.PxST('/bob/history/record-an-exchange', data, auth_as='alice')

    # tests
    # =====

    def test_success_is_302(self):
        actual = self.record_an_exchange('10', '0', 'foo').code
        assert actual == 302

    def test_non_admin_is_404(self):
        self.make_participant('alice', claimed_time=utcnow())
        self.make_participant('bob', claimed_time=utcnow())
        actual = self.record_an_exchange('10', '0', 'foo', make_participants=False).code
        assert actual == 404

    def test_non_post_is_405(self):
        self.make_participant('alice', claimed_time=utcnow(), is_admin=True)
        self.make_participant('bob', claimed_time=utcnow())
        actual = self.client.GxT( '/bob/history/record-an-exchange'
                                , auth_as='alice'
                                 ).code
        assert actual == 405

    def test_bad_amount_is_400(self):
        actual = self.record_an_exchange('cheese', '0', 'foo').code
        assert actual == 400

    def test_bad_fee_is_400(self):
        actual = self.record_an_exchange('10', 'cheese', 'foo').code
        assert actual == 400

    def test_no_note_is_400(self):
        actual = self.record_an_exchange('10', '0', '').code
        assert actual == 400

    def test_whitespace_note_is_400(self):
        actual = self.record_an_exchange('10', '0', '    ').code
        assert actual == 400

    def test_dropping_balance_below_zero_is_allowed_in_this_context(self):
        self.record_an_exchange('-10', '0', 'noted')
        actual = self.db.one("SELECT balance FROM participants WHERE username='bob'")
        assert actual == Decimal('-10.00')

    def test_success_records_exchange(self):
        self.record_an_exchange('10', '0.50', 'noted')
        expected = { "amount": Decimal('10.00')
                   , "fee": Decimal('0.50')
                   , "participant": "bob"
                   , "recorder": "alice"
                   , "note": "noted"
                    }
        SQL = "SELECT amount, fee, participant, recorder, note " \
              "FROM exchanges"
        actual = self.db.one(SQL, back_as=dict)
        assert actual == expected

    def test_success_updates_balance(self):
        self.record_an_exchange('10', '0', 'noted')
        expected = Decimal('10.00')
        SQL = "SELECT balance FROM participants WHERE username='bob'"
        actual = self.db.one(SQL)
        assert actual == expected

    def test_withdrawals_work(self):
        self.make_participant('alice', claimed_time=utcnow(), is_admin=True)
        self.make_participant('bob', claimed_time=utcnow(), balance=20)
        self.record_an_exchange('-7', '0', 'noted', make_participants=False)
        expected = Decimal('13.00')
        SQL = "SELECT balance FROM participants WHERE username='bob'"
        actual = self.db.one(SQL)
        assert actual == expected

    def test_withdrawals_take_fee_out_of_balance(self):
        self.make_participant('alice', claimed_time=utcnow(), is_admin=True)
        self.make_participant('bob', claimed_time=utcnow(), balance=20)
        self.record_an_exchange('-7', '1.13', 'noted', make_participants=False)
        SQL = "SELECT balance FROM participants WHERE username='bob'"
        assert self.db.one(SQL) == Decimal('11.87')

    def test_can_set_status(self):
        self.make_participants()
        for status in (None, 'pre', 'pending', 'failed', 'succeeded'):
            self.record_an_exchange('10', '0', 'noted', status, False)
            actual = self.db.one("SELECT status FROM exchanges ORDER BY timestamp desc LIMIT 1")
            assert actual == status

    def test_succeeded_affects_balance(self):
        self.record_an_exchange('10', '0', 'noted', 'succeeded')
        assert self.db.one("SELECT balance FROM participants WHERE username='bob'") == 10

    def test_non_succeeded_status_doesnt_affect_balance(self):
        self.make_participants()
        for status in (None, 'pre', 'pending', 'failed'):
            self.record_an_exchange('10', '0', 'noted', status, False)
            assert self.db.one("SELECT balance FROM participants WHERE username='bob'") == 0
