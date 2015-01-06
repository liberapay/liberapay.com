from __future__ import print_function, unicode_literals

from aspen import Response

from gratipay.security.user import SESSION
from gratipay.testing import Harness
from gratipay.wireup import find_files


class TestPages(Harness):

    def browse(self, **kw):
        alice = self.make_participant('alice', claimed_time='now')
        alice.insert_into_communities(True, 'Wonderland', 'wonderland')
        i = len(self.client.www_root)
        for spt in find_files(self.client.www_root, '*.spt'):
            url = spt[i:-4].replace('/%username/', 'alice') \
                           .replace('/for/%slug/', '/for/wonderland/') \
                           .replace('/%platform/', '/github/') \
                           .replace('/%user_name/', '/Gratipay/')
            try:
                r = self.client.GET(url, **kw)
            except Response as r:
                pass
            assert r.code < 500

    def test_anon_can_browse(self):
        self.browse()

    def test_new_participant_can_browse(self):
        self.browse(auth_as='alice')

    def test_profile(self):
        self.make_participant('cheese', claimed_time='now')
        expected = "I'm grateful for gifts"
        actual = self.client.GET('/cheese/').body.decode('utf8') # deal with cent sign
        assert expected in actual

    def test_widget(self):
        self.make_participant('cheese', claimed_time='now')
        expected = "javascript: window.open"
        actual = self.client.GET('/cheese/widget.html').body
        assert expected in actual

    def test_bank_account(self):
        expected = "add<br> or change your bank account"
        actual = self.client.GET('/bank-account.html').body
        assert expected in actual

    def test_credit_card(self):
        expected = "add<br> or change your credit card"
        actual = self.client.GET('/credit-card.html').body
        assert expected in actual

    def test_github_associate(self):
        assert self.client.GxT('/on/github/associate').code == 400

    def test_twitter_associate(self):
        assert self.client.GxT('/on/twitter/associate').code == 400

    def test_about(self):
        expected = "give money every week"
        actual = self.client.GET('/about/').body
        assert expected in actual

    def test_about_stats(self):
        expected = "have joined Gratipay"
        actual = self.client.GET('/about/stats.html').body
        assert expected in actual

    def test_about_charts(self):
        expected = "Money transferred"
        actual = self.client.GET('/about/charts.html').body
        assert expected in actual

    def test_about_faq(self):
        expected = "What is Gratipay?"
        actual = self.client.GET('/about/faq.html').body.decode('utf8')
        assert expected in actual

    def test_about_teams(self):
        expected = "Teams"
        actual = self.client.GET('/about/teams/').body.decode('utf8')
        assert expected in actual

    def test_404(self):
        response = self.client.GET('/about/four-oh-four.html', raise_immediately=False)
        assert "Not Found" in response.body
        assert "{%" not in response.body

    def test_for_contributors_redirects_to_inside_gratipay(self):
        loc = self.client.GxT('/for/contributors/').headers['Location']
        assert loc == 'http://inside.gratipay.com/'

    def test_mission_statement_also_redirects(self):
        assert self.client.GxT('/for/contributors/mission-statement.html').code == 302

    def test_bank_account_json(self):
        assert self.client.GxT('/bank-account.json').code == 404

    def test_credit_card_json(self):
        assert self.client.GxT('/credit-card.json').code == 404

    def test_anonymous_sign_out_redirects(self):
        response = self.client.PxST('/sign-out.html')
        assert response.code == 302
        assert response.headers['Location'] == '/'

    def test_sign_out_overwrites_session_cookie(self):
        self.make_participant('alice')
        response = self.client.PxST('/sign-out.html', auth_as='alice')
        assert response.code == 302
        assert response.headers.cookie[SESSION].value == ''

    def test_sign_out_doesnt_redirect_xhr(self):
        self.make_participant('alice')
        response = self.client.PxST('/sign-out.html', auth_as='alice',
                                    HTTP_X_REQUESTED_WITH=b'XMLHttpRequest')
        assert response.code == 200

    def test_receipts_signed_in(self):
        self.make_participant('alice', claimed_time='now')
        self.db.run("INSERT INTO exchanges (id, participant, amount, fee) "
                    "VALUES(100,'alice',1,0.1)")
        request = self.client.GET("/alice/receipts/100.html", auth_as="alice")
        assert request.code == 200

    def test_account_page_available_balance(self):
        self.make_participant('alice', claimed_time='now')
        self.db.run("UPDATE participants SET balance = 123.00 WHERE username = 'alice'")
        actual = self.client.GET("/alice/account/", auth_as="alice").body
        expected = "123"
        assert expected in actual

    def test_giving_page(self):
        alice = self.make_participant('alice', claimed_time='now')
        bob = self.make_participant('bob', claimed_time='now')
        alice.set_tip_to(bob, "1.00")
        actual = self.client.GET("/alice/giving/", auth_as="alice").body
        expected = "bob"
        assert expected in actual

    def test_giving_page_shows_unclaimed(self):
        alice = self.make_participant('alice', claimed_time='now')
        emma = self.make_elsewhere('github', 58946, 'emma').participant
        alice.set_tip_to(emma, "1.00")
        actual = self.client.GET("/alice/giving/", auth_as="alice").body
        expected1 = "emma"
        expected2 = "Unclaimed"
        assert expected1 in actual
        assert expected2 in actual

    def test_giving_page_shows_cancelled(self):
        alice = self.make_participant('alice', claimed_time='now')
        bob = self.make_participant('bob', claimed_time='now')
        alice.set_tip_to(bob, "1.00")
        alice.set_tip_to(bob, "0.00")
        actual = self.client.GET("/alice/giving/", auth_as="alice").body
        assert "bob" in actual
        assert "Cancelled" in actual

    def test_new_participant_can_edit_profile(self):
        self.make_participant('alice', claimed_time='now')
        body = self.client.GET("/alice/", auth_as="alice").body
        assert b'Edit' in body
