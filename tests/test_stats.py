from datetime import datetime

from mock import patch

from gittip.billing.payday import Payday
from gittip import testing
from gittip import wireup
from tests import serve_request


class TestStatsPage(testing.GittipBaseTest):

    def get_stats_page(self):
        response = serve_request('/about/stats.html')
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
        a_friday = datetime(2012, 8, 10, 12, 00, 01)
        mock_datetime.utcnow.return_value = a_friday

        db = wireup.db()
        wireup.billing()
        pd = Payday(db)
        pd.start()

        body = self.get_stats_page()
        self.assertTrue("is changing hands <b>right now!</b>" in body)
        pd.end()

    def test_stats_description_accurate_outside_of_payday(self):
        """Test stats page outside of the payday running"""
        body = self.get_stats_page()
        self.assertTrue("is ready for <b>this Friday</b>" in body)
