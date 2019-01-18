from __future__ import absolute_import, division, print_function, unicode_literals

import json

import mock

from liberapay.billing.payday import Payday
from liberapay.elsewhere._base import UserInfo
from liberapay.models.account_elsewhere import AccountElsewhere
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.testing import EUR, Harness
import liberapay.testing.elsewhere as user_info_examples
from liberapay.utils import b64encode_s


def get_user_info_example(platform_name):
    r = getattr(user_info_examples, platform_name)()
    if isinstance(r, tuple) and len(r) == 2:
        return r
    return '', r


class TestElsewhere(Harness):

    def test_associate_csrf(self):
        response = self.client.GxT('/on/github/associate?state=49b7c66246c7')
        assert response.code == 400

    def test_associate_with_empty_cookie_raises_400(self):
        response = self.client.GxT(
            '/on/github/associate?state=deadbeef',
            cookies={'github_deadbeef': ''},
        )
        assert response.code == 400

    def test_extract_user_info(self):
        for platform in self.platforms:
            domain, user_info = get_user_info_example(platform.name)
            r = platform.extract_user_info(user_info, domain)
            assert isinstance(r, UserInfo)
            assert r.user_id is not None
            assert len(r.user_id) > 0

    @mock.patch('requests_oauthlib.OAuth2Session.fetch_token')
    @mock.patch('liberapay.elsewhere._base.Platform.get_user_self_info')
    @mock.patch('liberapay.elsewhere._base.Platform.get_user_info')
    def test_connect_success(self, gui, gusi, ft):
        alice = self.make_participant('alice', elsewhere='twitter')

        gusi.return_value = self.client.website.platforms.github.extract_user_info({'id': 2}, '')
        gui.return_value = self.client.website.platforms.github.extract_user_info({'id': 1}, '')
        ft.return_value = None

        then = b'/foobar'
        cookie = b64encode_s(json.dumps(['query_data', 'connect', b64encode_s(then), '2']))
        response = self.client.GxT('/on/github/associate?state=deadbeef',
                                   auth_as=alice,
                                   cookies={'github_deadbeef': cookie})
        assert response.code == 302, response.text
        assert response.headers[b'Location'] == then

    @mock.patch('requests_oauthlib.OAuth2Session.fetch_token')
    @mock.patch('liberapay.elsewhere._base.Platform.get_user_self_info')
    @mock.patch('liberapay.elsewhere._base.Platform.get_user_info')
    def test_connect_might_need_confirmation(self, gui, gusi, ft):
        alice = self.make_participant('alice')
        self.make_participant('bob')

        gusi.return_value = self.client.website.platforms.github.extract_user_info({'id': 2}, '')
        gui.return_value = self.client.website.platforms.github.extract_user_info({'id': 1}, '')
        ft.return_value = None

        cookie = b64encode_s(json.dumps(['query_data', 'connect', '', '2']))
        response = self.client.GxT('/on/github/associate?state=deadbeef',
                                   auth_as=alice,
                                   cookies={'github_deadbeef': cookie})
        assert response.code == 302
        assert response.headers[b'Location'].startswith(b'/on/confirm.html?id=')

    def test_connect_failure(self):
        alice = self.make_participant('alice')
        error = 'User canceled the Dialog flow'
        url = '/on/facebook/associate?error_message=%s&state=deadbeef' % error
        cookie = b64encode_s(json.dumps(['query_data', 'connect', '', '2']))
        response = self.client.GxT(url, auth_as=alice,
                                   cookies={'facebook_deadbeef': cookie})
        assert response.code == 502, response.text
        assert error in response.text

    def test_redirect_csrf(self):
        response = self.client.GxT('/on/github/redirect')
        assert response.code == 405

    def test_redirects(self):
        data = dict(action='lock', then='/', user_id='')
        for i, platform in enumerate(self.platforms):
            platform.get_auth_url = lambda *a, **kw: ('', '', '')
            response = self.client.PxST('/on/%s/redirect' % platform.name, data,
                                        REMOTE_ADDR=b'0.0.0.%i' % i)
            assert response.code == 302

    def test_upsert(self):
        for platform in self.platforms:
            domain, user_info = get_user_info_example(platform.name)
            account = AccountElsewhere.upsert(platform.extract_user_info(user_info, domain))
            assert isinstance(account, AccountElsewhere)

    @mock.patch('liberapay.elsewhere._base.Platform.get_user_info')
    def test_user_pages(self, get_user_info):
        for platform in self.platforms:
            alice = UserInfo(platform=platform.name, user_id='0',
                             user_name='alice', is_team=False, domain='')
            get_user_info.side_effect = lambda *a: alice
            response = self.client.GET('/on/%s/alice/' % platform.name)
            assert response.code == 200

    @mock.patch('liberapay.elsewhere._base.Platform.get_user_info')
    def test_user_page_shows_pledges(self, get_user_info):
        alice = self.make_elsewhere('github', 1, 'alice').participant
        bob = self.make_participant('bob')
        carl = self.make_participant('carl')
        # bob needs to be an active donor for his pledge to be counted
        bob.set_tip_to(carl, EUR('1.00'))
        bob_card = ExchangeRoute.insert(
            bob, 'stripe-card', 'x', 'chargeable', remote_user_id='x'
        )
        self.add_payment_account(carl, 'stripe')
        self.make_payin_and_transfer(bob_card, carl, EUR('1.00'))
        Payday.start().run()
        # okay, let's check
        amount = EUR('14.97')
        bob.set_tip_to(alice, amount)
        assert alice.receiving == amount
        r = self.client.GET('/on/github/alice/')
        assert str(amount.amount) in r.text, r.text

    @mock.patch('liberapay.elsewhere._base.Platform.get_user_info')
    def test_user_page_doesnt_fail_on_at_sign(self, get_user_info):
        def f(domain, k, v, *a):
            if (domain, k, v) == ('', 'user_name', 'alice'):
                return UserInfo(
                    platform='twitter', user_id='0', user_name='alice',
                    is_team=False, domain=''
                )
            raise Exception
        get_user_info.side_effect = f
        response = self.client.GET('/on/twitter/@alice/')
        assert response.code == 200

    def test_user_pages_not_found(self):
        user_name = 'adhsjakdjsdkjsajdhksda'
        error = "There doesn't seem to be a user named %s on %s."
        for platform in self.platforms:
            if not hasattr(platform, 'api_user_name_info_path') or not platform.single_domain:
                continue
            r = self.client.GxT("/on/%s/%s/" % (platform.name, user_name))
            assert r.code == 404
            expected = error % (user_name, platform.display_name)
            assert expected in r.text

    def test_user_pages_xss(self):
        user_name = ">'>\"><img src=x onerror=alert(0)>"
        for platform in self.platforms:
            if not hasattr(platform, 'api_user_name_info_path') or not platform.single_domain:
                continue
            r = self.client.GET("/on/%s/%s/" % (platform.name, user_name), raise_immediately=False)
            assert r.code in (400, 404)

    def test_tip_form_is_in_pledge_page(self):
        self.make_elsewhere('twitter', -1, 'alice')
        body = self.client.GET('/on/twitter/alice/').text
        assert 'action="/~1/tip"' in body

    def test_failure_page_accepts_valid_username(self):
        self.client.GET('/on/github/liberapay/')  # normal case will have the db primed
        response = self.client.GET('/on/github/liberapay/failure.html')
        assert response.code == 200

    def test_public_json_not_opted_in(self):
        for platform in self.platforms:
            self.make_elsewhere(platform.name, 1, 'alice')
            response = self.client.GET('/on/%s/alice/public.json' % platform.name)

            assert response.code == 200

            data = json.loads(response.text)
            assert data['npatrons'] == 0

    def test_public_json_opted_in(self):
        self.make_participant('alice', elsewhere='github')
        response = self.client.GxT('/on/github/alice/public.json')
        assert response.code == 302


class TestConfirmTakeOver(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.alice_elsewhere = self.make_elsewhere('twitter', -1, 'alice')
        token, expires = self.alice_elsewhere.make_connect_token()
        self.connect_cookie = {'connect_%s' % self.alice_elsewhere.id: token}
        self.bob = self.make_participant('bob')

    def test_confirm(self):
        url = '/on/confirm.html?id=%s' % self.alice_elsewhere.id

        response = self.client.GxT(url)
        assert response.code == 403

        response = self.client.GxT(url, auth_as=self.bob)
        assert response.code == 400
        assert response.text.endswith(' value None in request cookies is invalid or unsupported')

        response = self.client.GET(url, auth_as=self.bob, cookies=self.connect_cookie)
        assert response.code == 200
        assert 'Please Confirm' in response.text

    def test_take_over(self):
        data = {'account_id': str(self.alice_elsewhere.id), 'should_transfer': 'yes'}

        response = self.client.PxST('/on/take-over.html', data=data)
        assert response.code == 403

        response = self.client.PxST('/on/take-over.html', data=data, auth_as=self.bob)
        assert response.code == 400
        assert response.text.endswith(' value None in request cookies is invalid or unsupported')

        response = self.client.PxST('/on/take-over.html', data=data, auth_as=self.bob,
                                    cookies=self.connect_cookie)
        assert response.code == 302
        assert response.headers[b'Location'] == b'/bob/edit'


class TestFriendFinder(Harness):

    def test_twitter_get_friends_for(self):
        platform = self.platforms.twitter
        user_info = platform.extract_user_info(user_info_examples.twitter(), '')
        account = AccountElsewhere.upsert(user_info)
        friends, nfriends, pages_urls = platform.get_friends_for(account)
        assert friends
        assert nfriends > 0

    def test_github_get_friends_for(self):
        platform = self.platforms.github
        user_info = platform.extract_user_info(user_info_examples.github(), '')
        account = AccountElsewhere.upsert(user_info)
        friends, nfriends, pages_urls = platform.get_friends_for(account)
        assert friends
        assert nfriends == len(friends) or nfriends == -1


class TestElsewhereDelete(Harness):

    def test_delete_nonexistent(self):
        alice = self.make_participant('alice', elsewhere='twitter')
        data = {'platform': 'twitter', 'user_id': 'nonexistent'}
        response = self.client.POST('/alice/elsewhere/delete', data, auth_as=alice,
                                    raise_immediately=False)
        assert response.code == 400
        assert "doesn&#39;t exist" in response.text

    def test_delete(self):
        platform = 'twitter'
        alice = self.make_participant('alice', elsewhere=platform)
        self.make_elsewhere('github', '1', 'alice')
        alice.take_over(('github', '', '1'))
        data = dict(platform=platform, user_id=str(alice.id))
        response = self.client.PxST('/alice/elsewhere/delete', data, auth_as=alice)
        assert response.code == 302
