# coding: utf8

from __future__ import print_function, unicode_literals

from collections import OrderedDict
from decimal import Decimal as D
import re

from aspen import Response

from liberapay.constants import SESSION
from liberapay.testing.mangopay import MangopayHarness
from liberapay.utils import b64encode_s, find_files


overescaping_re = re.compile(r'&amp;(#[0-9]{4}|[a-z]+);')


class TestPages(MangopayHarness):

    @classmethod
    def setUpClass(cls):
        super(TestPages, cls).setUpClass()
        i = len(cls.client.www_root)

        def f(spt):
            if spt[spt.rfind('/')+1:].startswith('index.'):
                return spt[i:spt.rfind('/')+1]
            return spt[i:-4]
        urls = OrderedDict()
        for url in sorted(map(f, find_files(cls.client.www_root, '*.spt'))):
            url = url.replace('/%username/membership/', '/team/membership/') \
                     .replace('/for/%name/', '/for/wonderland/') \
                     .replace('/%platform/', '/github/') \
                     .replace('/%user_name/', '/liberapay/') \
                     .replace('/%action', '/leave') \
                     .replace('/%redirect_to', '/giving') \
                     .replace('/%back_to', '/Li4=') \
                     .replace('/%type', '/receiving.js') \
                     .replace('/%endpoint', '/public')
            urls[url.replace('/%username/', '/david/')] = None
            urls[url.replace('/%username/', '/team/')] = None
        cls.urls = list(urls)

    def browse_setup(self):
        self.team = self.make_participant('team', kind='group')
        self.exchange_id = self.make_exchange('mango-cc', 19, 0, self.david)
        c = self.david.create_community('Wonderland')
        self.david.update_community_status('memberships', True, c.id)
        self.team.add_member(self.david)

    def browse(self, **kw):
        for url in self.urls:
            url = url.replace('/%exchange_id.int', '/%s' % self.exchange_id)
            assert '/%' not in url
            try:
                r = self.client.GET(url, **kw)
            except Response as r:
                if r.code == 404 or r.code >= 500:
                    raise
            assert r.code != 404
            assert r.code < 500
            assert not overescaping_re.search(r.text)

    def test_anon_can_browse_in_french(self):
        self.browse_setup()
        self.browse(HTTP_ACCEPT_LANGUAGE=b'fr')

    def test_new_participant_can_browse(self):
        self.browse_setup()
        self.browse(auth_as=self.david)

    def test_active_participant_can_browse(self):
        self.browse_setup()
        bob = self.make_participant('bob', balance=50)
        bob.set_tip_to(self.david, D('1.00'))
        self.david.set_tip_to(bob, D('0.50'))
        self.browse(auth_as=self.david)

    def test_homepage_in_all_supported_langs(self):
        self.make_participant('alice')
        self.db.run("UPDATE participants SET join_time = now() - INTERVAL '1 hour'")
        for _, l, _, _ in self.client.website.lang_list:
            r = self.client.GET('/', HTTP_ACCEPT_LANGUAGE=l.encode('ascii'))
            assert r.code == 200, r.text

        link_default = '<link rel="alternate" hreflang="x-default" href="%s/" />'
        link_default %= self.website.canonical_url
        assert link_default in r.text
        link_lang = '<link rel="alternate" hreflang="{0}" href="{1}://{0}.{2}/" />'
        link_lang = link_lang.format(l, self.website.canonical_scheme, self.website.canonical_host)
        assert link_lang in r.text

    def test_escaping_on_homepage(self):
        alice = self.make_participant('alice')
        expected = "<a href='/alice/edit'>"
        actual = self.client.GET('/', auth_as=alice).text
        assert expected in actual, actual

    def test_donate_link_is_in_profile_page(self):
        self.make_participant('alice')
        body = self.client.GET('/alice/').text
        assert 'href="/alice/donate"' in body

    def test_github_associate(self):
        assert self.client.GxT('/on/github/associate').code == 400

    def test_twitter_associate(self):
        assert self.client.GxT('/on/twitter/associate').code == 400

    def test_404(self):
        response = self.client.GET('/about/four-oh-four.html', raise_immediately=False)
        assert "Not Found" in response.text
        assert "{%" not in response.text

    def test_anonymous_sign_out_redirects(self):
        response = self.client.PxST('/sign-out.html')
        assert response.code == 302
        assert response.headers['Location'] == '/'

    def test_sign_out_overwrites_session_cookie(self):
        alice = self.make_participant('alice')
        response = self.client.PxST('/sign-out.html', auth_as=alice)
        assert response.code == 302
        assert response.headers.cookie[SESSION].value == ''

    def test_sign_out_doesnt_redirect_xhr(self):
        alice = self.make_participant('alice')
        response = self.client.PxST('/sign-out.html', auth_as=alice, xhr=True)
        assert response.code == 200

    def test_giving_page(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, "1.00")
        actual = self.client.GET("/alice/giving/", auth_as=alice).text
        expected = "bob"
        assert expected in actual

    def test_giving_page_shows_pledges(self):
        alice = self.make_participant('alice')
        emma = self.make_elsewhere('github', 58946, 'emma').participant
        alice.set_tip_to(emma, "1.00")
        actual = self.client.GET("/alice/giving/", auth_as=alice).text
        expected1 = "emma"
        expected2 = "Pledges"
        assert expected1 in actual
        assert expected2 in actual

    def test_giving_page_shows_cancelled(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, "1.00")
        alice.set_tip_to(bob, "0.00")
        actual = self.client.GET("/alice/giving/", auth_as=alice).text
        assert "bob" in actual
        assert "Cancelled" in actual

    def test_new_participant_can_edit_profile(self):
        alice = self.make_participant('alice')
        body = self.client.GET("/alice/", auth_as=alice).text
        assert b'Edit' in body

    def test_unicode_success_message_doesnt_break_edit_page(self):
        alice = self.make_participant('alice')
        for msg in ('épopée', b'épopée'):
            r = self.client.GET('/alice/edit?success='+b64encode_s(msg),
                                auth_as=alice)
            assert b'épopée' in r.body

    def test_can_see_payout_failure_page(self):
        error = 'error message #94355731569'
        eid = self.make_exchange('mango-ba', 19, 0, self.david, 'failed', error)
        r = self.client.GET('/david/wallet/payout/?exchange_id=%s' % eid,
                            auth_as=self.david)
        assert r.code == 200
        assert error in r.body.decode('utf8')

    def test_can_see_payout_success_page(self):
        eid = self.make_exchange('mango-ba', 19, 0, self.david)
        r = self.client.GET('/david/wallet/payout/?exchange_id=%s' % eid,
                            auth_as=self.david)
        assert r.code == 200
        assert '€19' in r.body.decode('utf8')

    def test_identity_form(self):
        janeway = self.make_participant(
            'janeway', email='janeway@example.org', mangopay_user_id=None,
            mangopay_wallet_id=None,
        )
        assert janeway.mangopay_user_id is None

        # Create a mangopay natural user
        user_data = {
            'FirstName': 'Kathryn',
            'LastName': 'Janeway',
            'CountryOfResidence': 'US',
            'Nationality': 'IS',
            'Birthday': '1995-01-16',
        }
        data = dict(user_data, terms='agree')
        kw = dict(auth_as=janeway, raise_immediately=False, xhr=True)
        r = self.client.POST('/janeway/identity', data, **kw)
        assert r.code == 200, r.text
        janeway = janeway.refetch()
        assert janeway.mangopay_user_id

        # Edit the natural user
        data2 = dict(data, Nationality='US')
        r = self.client.POST('/janeway/identity', data2, **kw)
        assert r.code == 200, r.text
        janeway2 = janeway.refetch()
        assert janeway2.mangopay_user_id == janeway.mangopay_user_id

        # Create a mangopay legal user
        self.db.run("UPDATE participants SET kind = 'organization'")
        self.db.run("UPDATE participants SET mangopay_user_id = mangopay_wallet_id = NULL")
        data = {'LegalRepresentative'+k: v for k, v in user_data.items()}
        data['LegalPersonType'] = 'BUSINESS'
        data['Name'] = 'Starfleet'
        data['terms'] = 'agree'
        r = self.client.POST('/janeway/identity', data, **kw)
        assert r.code == 200, r.text
        janeway = janeway.refetch()
        assert janeway.mangopay_user_id

        # Edit the legal user
        data2 = dict(data, LegalPersonType='ORGANIZATION')
        r = self.client.POST('/janeway/identity', data2, **kw)
        assert r.code == 200, r.text
        janeway2 = janeway.refetch()
        assert janeway2.mangopay_user_id == janeway.mangopay_user_id
