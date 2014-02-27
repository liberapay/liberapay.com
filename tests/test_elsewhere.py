from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.elsewhere import UserInfo
from gittip.models.account_elsewhere import AccountElsewhere
from gittip.testing import Harness
import gittip.testing.elsewhere as user_info_examples


class Tests(Harness):

    def test_associate_csrf(self):
        response = self.client.GxT('/on/github/associate?state=49b7c66246c7')
        assert response.code == 400

    def test_extract_user_info(self):
        for platform in self.platforms:
            user_info = getattr(user_info_examples, platform.name)()
            r = platform.extract_user_info(user_info)
            assert isinstance(r, UserInfo)
            assert r.user_id is not None
            assert len(r.user_id) > 0
            assert r.user_name is not None
            assert len(r.user_name) > 0

    def test_opt_in_can_change_username(self):
        account = self.make_elsewhere('twitter', 1, 'alice')
        expected = 'bob'
        actual = account.opt_in('bob')[0].participant.username
        assert actual == expected

    def test_opt_in_doesnt_have_to_change_username(self):
        self.make_participant('bob')
        account = self.make_elsewhere('twitter', 1, 'alice')
        expected = account.participant.username # A random one.
        actual = account.opt_in('bob')[0].participant.username
        assert actual == expected

    def test_redirect_csrf(self):
        response = self.client.GxT('/on/github/redirect')
        assert response.code == 405

    def test_redirects(self, *classes):
        self.make_participant('alice')
        data = dict(action='opt-in', then='/', user_name='')
        for platform in self.platforms:
            platform.get_auth_url = lambda *a, **kw: ('', '', '')
            response = self.client.PxST('/on/%s/redirect' % platform.name,
                                        data, auth_as='alice')
            assert response.code == 302

    def test_upsert(self):
        for platform in self.platforms:
            user_info = getattr(user_info_examples, platform.name)()
            account = platform.upsert(platform.extract_user_info(user_info))
            assert isinstance(account, AccountElsewhere)

    def test_user_pages(self):
        alice = UserInfo(user_id='0', user_name='alice', is_team=False)
        for platform in self.platforms:
            platform.get_user_info = lambda *a: alice
            response = self.client.GET('/on/%s/alice/' % platform.name)
            assert response.code == 200
            assert 'has not joined' in response.body.decode('utf8')
