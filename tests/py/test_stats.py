from __future__ import print_function, unicode_literals

import datetime
from decimal import Decimal
import json

from mock import patch

from gittip import wireup
from gittip.billing.payday import Payday
from gittip.models.participant import Participant
from gittip.testing import Harness


class TestCommaize(Harness):
    # XXX This really ought to be in helper methods test file
    def setUp(self):
        Harness.setUp(self)
        simplate = self.client.load_resource(b'/about/stats.html')
        self.commaize = simplate.pages[0]['commaize']

    def test_commaize_commaizes(self):
        actual = self.commaize(1000.0)
        assert actual == "1,000"

    def test_commaize_commaizes_and_obeys_decimal_places(self):
        actual = self.commaize(1000, 4)
        assert actual == "1,000.0000"


class TestChartOfReceiving(Harness):
    def setUp(self):
        Harness.setUp(self)
        for participant in ['alice', 'bob']:
            self.make_participant(participant, last_bill_result='')

    def test_get_tip_distribution_handles_a_tip(self):
        Participant.from_username('alice').set_tip_to('bob', '3.00')
        expected = ([[Decimal('3.00'), 1, Decimal('3.00'), 1.0, Decimal('1')]],
                    1.0, Decimal('3.00'))
        actual = Participant.from_username('bob').get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_no_tips(self):
        expected = ([], 0.0, Decimal('0.00'))
        actual = Participant.from_username('alice').get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_handles_multiple_tips(self):
        self.make_participant('carl', last_bill_result='')
        Participant.from_username('alice').set_tip_to('bob', '1.00')
        Participant.from_username('carl').set_tip_to('bob', '3.00')
        expected = ([
            [Decimal('1.00'), 1L, Decimal('1.00'), 0.5, Decimal('0.25')],
            [Decimal('3.00'), 1L, Decimal('3.00'), 0.5, Decimal('0.75')]
        ], 2.0, Decimal('4.00'))
        actual = Participant.from_username('bob').get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_bad_cc(self):
        self.make_participant('bad_cc', last_bill_result='Failure!')
        Participant.from_username('alice').set_tip_to('bob', '1.00')
        Participant.from_username('bad_cc').set_tip_to('bob', '3.00')
        expected = ([[Decimal('1.00'), 1L, Decimal('1.00'), 1, Decimal('1')]],
                    1.0, Decimal('1.00'))
        actual = Participant.from_username('bob').get_tip_distribution()
        assert actual == expected

    def test_get_tip_distribution_ignores_missing_cc(self):
        self.make_participant('missing_cc', last_bill_result=None)
        Participant.from_username('alice').set_tip_to('bob', '1.00')
        Participant.from_username('missing_cc').set_tip_to('bob', '3.00')
        expected = ([[Decimal('1.00'), 1L, Decimal('1.00'), 1, Decimal('1')]],
                    1.0, Decimal('1.00'))
        actual = Participant.from_username('bob').get_tip_distribution()
        assert actual == expected

class TestJson(Harness):

    def test_200(self):
        response = self.client.GET('/about/stats.json')
        assert response.code == 200
        body = json.loads(response.body)
        assert len(body) > 0

class TestRenderingStatsPage(Harness):
    def get_stats_page(self):
        return self.client.GET('/about/stats.html').body

    def test_stats_description_accurate_during_payday_run(self):
        """Test that stats page takes running payday into account.

        This test was originally written to expose the fix required for
        https://github.com/gittip/www.gittip.com/issues/92.
        """

        # Hydrating a website requires a functioning datetime module.
        self.client.hydrate_website()

        a_thursday = datetime.datetime(2012, 8, 9, 11, 00, 01)
        with patch.object(datetime, 'datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = a_thursday

            env = wireup.env()
            wireup.billing(env)
            payday = Payday(self.db)
            payday.start()

            body = self.get_stats_page()
            assert "is changing hands <b>right now!</b>" in body, body
            payday.end()

    def test_stats_description_accurate_outside_of_payday(self):
        """Test stats page outside of the payday running"""

        # Hydrating a website requires a functioning datetime module.
        self.client.hydrate_website()

        a_monday = datetime.datetime(2012, 8, 6, 11, 00, 01)
        with patch.object(datetime, 'datetime') as mock_datetime:
            mock_datetime.utcnow.return_value = a_monday

            payday = Payday(self.db)
            payday.start()

            body = self.get_stats_page()
            assert "is ready for <b>this Thursday</b>" in body, body
            payday.end()
