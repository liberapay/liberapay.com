from __future__ import unicode_literals

import json

from gittip.billing.payday import Payday
from gittip.testing import Harness


class Tests(Harness):

    def test_paydays_json_gives_paydays(self):
        Payday(self.db).start()
        self.make_participant("alice")

        response = self.client.GET("/about/paydays.json")
        paydays = json.loads(response.body)
        assert paydays[0]['ntippers'] == 0
