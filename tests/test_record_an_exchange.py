from __future__ import unicode_literals
from decimal import Decimal

from aspen.utils import utcnow
from gittip.testing import Harness
from gittip.testing.client import TestClient


class TestRecordAnExchange(Harness):

    # fixture
    # =======

    def setUp(self):
        super(Harness, self).setUp()
        self.client = TestClient()

    def get_csrf_token(self):
        response = self.client.get('/')
        return response.request.context['csrf_token']

    def record_an_exchange(self, amount, fee, note, make_participants=True):
        if make_participants:
            now = utcnow()
            self.make_participant('alice', claimed_time=now, is_admin=True)
            self.make_participant('bob', claimed_time=now)
        return self.client.post( '/bob/history/record-an-exchange'
                               , { 'amount': amount, 'fee': fee, 'note': note
                                 , 'csrf_token': self.get_csrf_token()
                                  }
                               , 'alice'
                                )

    # tests
    # =====

    def test_success_is_302(self):
        actual = self.record_an_exchange('10', '0', 'foo').code
        assert actual == 302, actual

    def test_non_admin_is_404(self):
        self.make_participant('alice', claimed_time=utcnow())
        self.make_participant('bob', claimed_time=utcnow())
        actual = self.record_an_exchange('10', '0', 'foo', False).code
        assert actual == 404, actual

    def test_non_post_is_405(self):
        self.make_participant('alice', claimed_time=utcnow(), is_admin=True)
        self.make_participant('bob', claimed_time=utcnow())
        actual = \
               self.client.get('/bob/history/record-an-exchange', 'alice').code
        assert actual == 405, actual

    def test_bad_amount_is_400(self):
        actual = self.record_an_exchange('cheese', '0', 'foo').code
        assert actual == 400, actual

    def test_bad_fee_is_400(self):
        actual = self.record_an_exchange('10', 'cheese', 'foo').code
        assert actual == 400, actual

    def test_no_note_is_400(self):
        actual = self.record_an_exchange('10', '0', '').code
        assert actual == 400, actual

    def test_whitespace_note_is_400(self):
        actual = self.record_an_exchange('10', '0', '    ').code
        assert actual == 400, actual

    def test_dropping_balance_below_zero_is_500(self):
        actual = self.record_an_exchange('-10', '0', 'noted').code
        assert actual == 500, actual

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
        assert actual == expected, actual

    def test_success_updates_balance(self):
        self.record_an_exchange('10', '0', 'noted')
        expected = Decimal('10.00')
        SQL = "SELECT balance FROM participants WHERE username='bob'"
        actual = self.db.one(SQL)
        assert actual == expected, actual

    def test_withdrawals_work(self):
        self.make_participant('alice', claimed_time=utcnow(), is_admin=True)
        self.make_participant('bob', claimed_time=utcnow(), balance=20)
        self.record_an_exchange('-7', '0', 'noted', False)
        expected = Decimal('13.00')
        SQL = "SELECT balance FROM participants WHERE username='bob'"
        actual = self.db.one(SQL)
        assert actual == expected, actual
