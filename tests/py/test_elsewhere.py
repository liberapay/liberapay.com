from __future__ import absolute_import, division, print_function, unicode_literals

import json
from base64 import b64encode

import mock
from gratipay.elsewhere import UserInfo
from gratipay.models.account_elsewhere import AccountElsewhere
from gratipay.models.participant import Participant
from gratipay.testing import Harness
import gratipay.testing.elsewhere as user_info_examples


class TestElsewhere(Harness):

    def test_associate_csrf(self):
        response = self.client.GxT('/on/github/associate?state=49b7c66246c7')
        assert response.code == 400

    def test_associate_with_empty_cookie_raises_400(self):
        self.client.cookie[b'github_deadbeef'] = b''
        response = self.client.GxT('/on/github/associate?state=deadbeef')
        assert response.code == 400

    def test_extract_user_info(self):
        for platform in self.platforms:
            user_info = getattr(user_info_examples, platform.name)()
            r = platform.extract_user_info(user_info)
            assert isinstance(r, UserInfo)
            assert r.user_id is not None
            assert len(r.user_id) > 0

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

    def test_opt_in_resets_is_closed_to_false(self):
        alice = self.make_elsewhere('twitter', 1, 'alice')
        alice.participant.update_is_closed(True)
        user = alice.opt_in('alice')[0]
        assert not user.participant.is_closed
        assert not Participant.from_username('alice').is_closed

    def test_logging_in_doesnt_reset_goal(self):
        self.make_participant('alice', claimed_time='now', elsewhere='twitter', goal=100)
        alice = AccountElsewhere.from_user_name('twitter', 'alice').opt_in('alice')[0].participant
        assert alice.goal == 100

    def test_hitting_confirm_plain_results_in_404(self):
        assert self.client.GxT('/on/confirm.html').code == 404

    @mock.patch('requests_oauthlib.OAuth2Session.fetch_token')
    @mock.patch('gratipay.elsewhere.Platform.get_user_self_info')
    @mock.patch('gratipay.elsewhere.Platform.get_user_info')
    def test_connect_might_need_confirmation(self, gui, gusi, ft):
        self.make_participant('alice', claimed_time='now')
        self.make_participant('bob', claimed_time='now')

        gusi.return_value = self.client.website.platforms.github.extract_user_info({'id': 2})
        gui.return_value = self.client.website.platforms.github.extract_user_info({'id': 1})
        ft.return_value = None

        self.client.cookie[b'github_deadbeef'] = b64encode(json.dumps([ 'query_data'
                                                                      , 'connect'
                                                                      , ''
                                                                      , 'bob'
                                                                       ]))
        response = self.client.GxT('/on/github/associate?state=deadbeef', auth_as='alice')
        assert response.code == 200
        assert "Please Confirm" in response.body

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
            account = AccountElsewhere.upsert(platform.extract_user_info(user_info))
            assert isinstance(account, AccountElsewhere)

    def test_user_pages(self):
        for platform in self.platforms:
            alice = UserInfo( platform=platform.name
                            , user_id='0'
                            , user_name='alice'
                            , is_team=False
                            )
            platform.get_user_info = lambda *a: alice
            response = self.client.GET('/on/%s/alice/' % platform.name)
            assert response.code == 200
            assert 'has not joined' in response.body.decode('utf8')


    def test_failure_page_requires_valid_username(self):
        response = self.client.GxT('/on/twitter/nmjhgfcftyuikjnbvftyujhbgtfgh/failure.html?action')
        assert response.code == 404

    def test_failure_page_accepts_valid_username(self):
        self.client.GET('/on/twitter/Gratipay/')  # normal case will have the db primed
        response = self.client.GET('/on/twitter/Gratipay/failure.html?action')
        assert response.code == 200
