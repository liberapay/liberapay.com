from __future__ import unicode_literals
import mock

import balanced

from gittip import authentication, billing

from tests import GittipBaseDBTest


class TestBilling(GittipBaseDBTest):
    def setUp(self):
        super(TestBilling, self).setUp()
        self.participant_id = 'lgtest'
        self.pp_customer_id = '/v1/marketplaces/M123/accounts/A123'
        self.tok = '/v1/marketplaces/M123/accounts/A123/cards/C123'
        billing.db = self.db

    @mock.patch('balanced.Account')
    def test_associate_valid(self, ba):
        not_found = balanced.exc.NoResultFound()
        ba.query.filter.return_value.one.side_effect = not_found
        ba.return_value.save.return_value.uri = self.pp_customer_id

        # first time through, payment processor account is None
        billing.associate(self.participant_id, None, self.tok)

        expected_email_address = '{}@gittip.com'.format(
            self.participant_id
        )
        _, kwargs = balanced.Account.call_args
        self.assertTrue(kwargs['email_address'], expected_email_address)

        user = authentication.User.from_id(self.participant_id)
        # participant in db should be updated
        self.assertEqual(user.session['pp_customer_id'], self.pp_customer_id)

    @mock.patch('balanced.Account')
    def test_associate_invalid_card(self, ba):
        error_message = 'Something terrible'
        not_found = balanced.exc.HTTPError(error_message)
        ba.find.return_value.save.side_effect = not_found

        # second time through, payment processor account is balanced
        # account_uri
        billing.associate(self.participant_id, self.pp_customer_id, self.tok)

        user = authentication.User.from_id(self.participant_id)
        # participant in db should be updated to reflect the error message of
        # last uppepdate
        self.assertEqual(user.session['last_bill_result'], error_message)
        self.assertTrue(ba.find.call_count)
