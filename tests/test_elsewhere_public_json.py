from __future__ import print_function, unicode_literals

import json
#import datetime

#import pytz
from gittip.testing import Harness


class Tests(Harness):

    def test_returns_json_if_not_opted_in(self, *classes):
        for platform in self.platforms:
            self.make_elsewhere(platform.name, 1, 'alice')
            response = self.client.GET('/on/%s/alice/public.json' % platform.name)

            assert response.code == 200

            data = json.loads(response.body)
            assert data['on'] == platform.name

    def test_redirect_if_opted_in(self, *classes):
        self.make_participant('alice')
        for platform in self.platforms:
            account = self.make_elsewhere(platform.name, 1, 'alice')
            account.opt_in('alice')

            response = self.client.GxT('/on/%s/alice/public.json' % platform.name)

            assert response.code == 302
