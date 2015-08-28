from __future__ import print_function, unicode_literals

import re
from decimal import Decimal as D

from aspen import Response

from liberapay.constants import SESSION
from liberapay.testing import Harness
from liberapay.wireup import find_files


overescaping_re = re.compile(r'&amp;(#[0-9]{4}|[a-z]+);')


class TestPages(Harness):

    def browse_setup(self):
        self.alice = self.make_participant('alice')
        self.team = self.make_participant('team', kind='group')
        self.exchange_id = self.make_exchange('balanced-cc', 19, 0, self.alice)
        self.alice.insert_into_communities(True, 'Wonderland', 'wonderland')
        self.team.add_member(self.alice)

    def browse(self, **kw):
        i = len(self.client.www_root)
        def f(spt):
            if spt[spt.rfind('/')+1:].startswith('index.'):
                return spt[i:spt.rfind('/')+1]
            return spt[i:-4]
        for url in sorted(map(f, find_files(self.client.www_root, '*.spt'))):
            url = url.replace('/%username/members/', '/team/members/') \
                     .replace('/%username/', '/alice/') \
                     .replace('/for/%slug/', '/for/wonderland/') \
                     .replace('/%platform/', '/github/') \
                     .replace('/%user_name/', '/liberapay/') \
                     .replace('/%membername', '/alice') \
                     .replace('/%exchange_id.int', '/%s' % self.exchange_id) \
                     .replace('/%redirect_to', '/giving') \
                     .replace('/%endpoint', '/public')
            assert '/%' not in url
            try:
                r = self.client.GET(url, **kw)
            except Response as r:
                if r.code == 404 or r.code >= 500:
                    raise
            assert r.code != 404
            assert r.code < 500
            assert not overescaping_re.search(r.body.decode('utf8'))

    def test_anon_can_browse(self):
        self.browse_setup()
        self.browse()

    def test_new_participant_can_browse(self):
        self.browse_setup()
        self.browse(auth_as=self.alice)

    def test_active_participant_can_browse(self):
        self.browse_setup()
        bob = self.make_participant('bob', last_bill_result='')
        bob.set_tip_to(self.alice, D('1.00'))
        self.alice.set_tip_to(bob, D('0.50'))
        self.browse(auth_as=self.alice)

    def test_escaping_on_homepage(self):
        alice = self.make_participant('alice')
        expected = "<a href='/alice/edit'>"
        actual = self.client.GET('/', auth_as=alice).body
        assert expected in actual, actual

    def test_username_is_in_unauth_giving_cta(self):
        self.make_participant('alice')
        body = self.client.GET('/alice/').body
        assert 'give to alice' in body

    def test_github_associate(self):
        assert self.client.GxT('/on/github/associate').code == 400

    def test_twitter_associate(self):
        assert self.client.GxT('/on/twitter/associate').code == 400

    def test_404(self):
        response = self.client.GET('/about/four-oh-four.html', raise_immediately=False)
        assert "Not Found" in response.body
        assert "{%" not in response.body

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
        response = self.client.PxST('/sign-out.html', auth_as=alice,
                                    HTTP_X_REQUESTED_WITH=b'XMLHttpRequest')
        assert response.code == 200

    def test_giving_page(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, "1.00")
        actual = self.client.GET("/alice/giving/", auth_as=alice).body
        expected = "bob"
        assert expected in actual

    def test_giving_page_shows_pledges(self):
        alice = self.make_participant('alice')
        emma = self.make_elsewhere('github', 58946, 'emma').participant
        alice.set_tip_to(emma, "1.00")
        actual = self.client.GET("/alice/giving/", auth_as=alice).body
        expected1 = "emma"
        expected2 = "Pledges"
        assert expected1 in actual
        assert expected2 in actual

    def test_giving_page_shows_cancelled(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, "1.00")
        alice.set_tip_to(bob, "0.00")
        actual = self.client.GET("/alice/giving/", auth_as=alice).body
        assert "bob" in actual
        assert "Cancelled" in actual

    def test_new_participant_can_edit_profile(self):
        alice = self.make_participant('alice')
        body = self.client.GET("/alice/", auth_as=alice).body
        assert b'Edit' in body

    def test_anon_bank_acc_page(self):
        body = self.client.GET("/alice/routes/bank-account.html").body
        assert "<h1>Bank Account</h1>" in body
