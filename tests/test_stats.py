from datetime import datetime
from decimal import Decimal

from mock import patch

import gittip
from gittip.billing.payday import Payday
from gittip import testing
from gittip import wireup


# commaize

simplate = testing.load_simplate('/about/stats.html')
commaize = simplate.pages[0]['commaize']

def test_commaize_commaizes():
    actual = commaize(1000.0)
    assert actual == "1,000", actual

def test_commaize_commaizes_and_obeys_decimal_places():
    actual = commaize(1000, 4)
    assert actual == "1,000.0000", actual


class HistogramOfGivingTests(testing.GittipBaseDBTest):
    def setUp(self):
        super(HistogramOfGivingTests, self).setUp()

        user_ids = [x[1] for x in testing.GITHUB_USERS]
        prices = (0, 1, 3, 6, 12, 24)
        donation_map = {
            'lgtest': {
                'lglocktest': 1,
                'gittip-test-0': 3,
                'gittip-test-1': 6,
                'gittip-test-2': 0,
                },
            'lglocktest': {
                'lgtest': 3,
                'gittip-test-0': 6,
                'gittip-test-1': 6,
                'gittip-test-2': 3,
                },
            'gittip-test-0': {
                'lgtest': 12,
                },
            'gittip-test-1': {
                'lgtest': 3,
                },
            'gittip-test-2': {
                'lgtest': 6,
                },
            'gittip-test-3': {
                },
        }
        for tipper, donation in donation_map.iteritems():
            if tipper != 'gittip-test-0':
                # Only people with a credit card on file should show up.
                self.db.execute(
                    "UPDATE participants SET last_bill_result='' WHERE id=%s",
                    (tipper,))
            for tippee, amount in donation.iteritems():
                self.db.execute(
                    "INSERT INTO tips (ctime, tipper, tippee, amount) " \
                    "VALUES (now(), %s, %s, %s);",
                    (tipper, tippee, amount))

    def test_histogram(self):
        expected = ( [ [ Decimal('3.00'), 2L, Decimal('6.00')
                       , 0.6666666666666666, Decimal('0.5')
                        ]
                     , [ Decimal('6.00'), 1L, Decimal('6.00')
                       , 0.3333333333333333, Decimal('0.5')
                        ]
                      ]
                   , 3.0
                   , Decimal('12.00')
                    )
        actual = gittip.get_histogram_of_giving('lgtest')
        self.assertEqual(expected, actual)

    def test_histogram_no_tips(self):
        expected = ([], 0.0, Decimal('0.00'))
        actual = gittip.get_histogram_of_giving('gittip-test-3')
        self.assertEqual(expected, actual)


# rendering

class TestStatsPage(testing.GittipBaseTest):

    def get_stats_page(self):
        response = testing.serve_request('/about/stats.html')
        return response.body

    def clear_paydays(self):
        "Clear all the existing paydays in the DB."
        from gittip import db
        db.execute("DELETE FROM paydays")

    @patch('datetime.datetime')
    def test_stats_description_accurate_during_payday_run(self, mock_datetime):
        """Test that stats page takes running payday into account.

        This test was originally written to expose the fix required for
        https://github.com/whit537/www.gittip.com/issues/92.
        """
        self.clear_paydays()
        a_thursday = datetime(2012, 8, 9, 12, 00, 01)
        mock_datetime.utcnow.return_value = a_thursday

        db = wireup.db()
        wireup.billing()
        pd = Payday(db)
        pd.start()

        body = self.get_stats_page()
        self.assertTrue("is changing hands <b>right now!</b>" in body)
        pd.end()

    @patch('datetime.datetime')
    def test_stats_description_accurate_outside_of_payday(self, mock_datetime):
        """Test stats page outside of the payday running"""
        self.clear_paydays()
        a_monday = datetime(2012, 8, 6, 12, 00, 01)
        mock_datetime.utcnow.return_value = a_monday

        db = wireup.db()
        wireup.billing()
        pd = Payday(db)
        pd.start()

        body = self.get_stats_page()
        self.assertTrue("is ready for <b>this Thursday</b>" in body)
        pd.end()
