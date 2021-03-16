from unittest.mock import patch

from pando import json
import stripe

from liberapay.billing.payday import Payday
from liberapay.constants import SESSION
from liberapay.testing import EUR
from liberapay.testing.mangopay import Harness
from liberapay.utils import b64encode_s
from liberapay.wireup import NoDB


class TestPages(Harness):

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

        assert r.headers[b'Content-Type'] == b'text/html; charset=UTF-8'

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

    def test_homepage_redirects_when_db_is_down(self):
        with patch.multiple(self.website, db=NoDB()):
            r = self.client.GET('/', raise_immediately=False)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/about/'

    def test_about_page_works_even_when_db_is_down(self):
        alice = self.make_participant('alice')
        with patch.multiple(self.website, db=NoDB()):
            r = self.client.GET('/about/', auth_as=alice)
        assert r.code == 200
        assert b"Liberapay is " in r.body

    def test_stats_page_is_503_when_db_is_down(self):
        with patch.multiple(self.website, db=NoDB()):
            r = self.client.GET('/about/stats', raise_immediately=False)
        assert r.code == 503
        assert b" technical failures." in r.body
        assert b" unable to process your request " in r.body

    def test_paydays_json_gives_paydays(self):
        Payday.start()
        self.make_participant("alice")

        response = self.client.GET("/about/paydays.json")
        paydays = json.loads(response.text)
        assert paydays[0]['ntippers'] == 0

    def test_404(self):
        response = self.client.GET('/about/four-oh-four.html', raise_immediately=False)
        assert "Not Found" in response.text
        assert "{%" not in response.text

    def test_anonymous_sign_out_redirects(self):
        response = self.client.PxST('/sign-out.html')
        assert response.code == 302
        assert response.headers[b'Location'] == b'/'

    def test_sign_out_expires_session(self):
        alice = self.make_participant('alice')
        sess = alice.session = alice.start_session()
        cookies = {SESSION: '%i:%i:%s' % (alice.id, sess.id, sess.secret)}
        response = self.client.GET('/alice/giving', cookies=cookies)
        assert response.code == 200
        response = self.client.PxST('/sign-out.html', cookies=cookies)
        assert response.code == 302
        assert response.headers.cookie[SESSION].value == ''
        response = self.client.GET('/alice/giving', cookies=cookies, raise_immediately=False)
        assert response.code == 403

    def test_sign_out_doesnt_redirect_xhr(self):
        alice = self.make_participant('alice')
        response = self.client.PxST('/sign-out.html', auth_as=alice, xhr=True)
        assert response.code == 200

    def test_giving_page(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, EUR('1.00'))
        actual = self.client.GET("/alice/giving/", auth_as=alice).text
        expected = "bob"
        assert expected in actual

    def test_giving_page_shows_pledges(self):
        alice = self.make_participant('alice')
        emma = self.make_elsewhere('github', 58946, 'emma').participant
        alice.set_tip_to(emma, EUR('1.00'))
        actual = self.client.GET("/alice/giving/", auth_as=alice).text
        expected1 = "emma"
        expected2 = "Pledges"
        assert expected1 in actual
        assert expected2 in actual

    def test_giving_page_shows_stopped_donations(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        alice.set_tip_to(bob, EUR('1.00'))
        alice.set_tip_to(bob, EUR('0.00'))
        actual = self.client.GET("/alice/giving/", auth_as=alice).text
        assert "bob" in actual
        assert "Discontinued donations (1)" in actual

    def test_giving_page_allows_hiding_stopped_tip(self):
        alice = self.make_participant('alice')
        bob = self.make_participant('bob')
        tip1 = alice.set_tip_to(bob, EUR('1.00'))
        assert tip1.hidden is None
        tip2 = alice.stop_tip_to(bob)
        assert tip2.hidden is None
        r = self.client.PxST('/alice/giving/', {"hide": str(bob.id)}, auth_as=alice)
        assert r.code == 302, r.text
        tip3 = alice.get_tip_to(bob)
        assert tip3.hidden is True
        assert tip3.amount == tip1.amount
        assert tip3.mtime > tip2.mtime
        r = self.client.GET('/alice/giving/', auth_as=alice)
        assert r.code == 200, r.text
        assert 'href="/bob' not in r.text
        assert 'Discontinued donations' not in r.text

    def test_new_participant_can_edit_profile(self):
        alice = self.make_participant('alice')
        body = self.client.GET("/alice/", auth_as=alice).text
        assert 'Edit' in body

    def test_unicode_success_message_doesnt_break_edit_page(self):
        alice = self.make_participant('alice')
        s = 'épopée'
        bs = s.encode('utf8')
        for msg in (s, bs):
            r = self.client.GET('/alice/edit/username?success='+b64encode_s(msg),
                                auth_as=alice)
            assert bs in r.body

    def test_about_me(self):
        r = self.client.GET('/about/me', raise_immediately=False)
        assert r.code == 403
        r = self.client.GET('/about/me/', raise_immediately=False)
        assert r.code == 403
        r = self.client.GET('/about/me/edit/username', raise_immediately=False)
        assert r.code == 403
        alice = self.make_participant('alice')
        r = self.client.GET('/about/me', auth_as=alice, raise_immediately=False)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/'
        r = self.client.GET('/about/me/', auth_as=alice, raise_immediately=False)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/'
        r = self.client.GET('/about/me/edit/username', auth_as=alice, raise_immediately=False)
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/edit/username'

    def test_payment_instruments_page(self):
        offset = 1000
        self.db.run("ALTER SEQUENCE participants_id_seq RESTART WITH %s", (offset,))
        self.db.run("ALTER SEQUENCE exchange_routes_id_seq RESTART WITH %s", (offset,))
        alice = self.make_participant('alice')
        r = self.client.GET('/alice/routes/', raise_immediately=False)
        assert r.code == 403, r.text
        r = self.client.GET('/alice/routes/', auth_as=alice)
        assert r.code == 200, r.text
        assert "You don&#39;t have any valid payment instrument." in r.text, r.text
        r = self.client.GET('/alice/routes/add?type=stripe-card', auth_as=alice)
        assert r.code == 200, r.text
        r = self.client.POST(
            '/alice/routes/add',
            {'stripe_pm_id': 'pm_card_visa', 'one_off': 'true'},
            auth_as=alice, raise_immediately=False,
        )
        assert r.code == 302, r.text
        r = self.client.GET('/alice/routes/', auth_as=alice)
        assert r.code == 200, r.text
        assert "You have 1 connected payment instrument." in r.text, r.text
        sepa_direct_debit_token = stripe.Token.create(bank_account=dict(
            country='BE',
            currency='EUR',
            account_number='BE62510007547061',
            account_holder_name='Dupond et Dupont',
        ))
        r = self.client.POST(
            '/alice/routes/add?type=stripe-sdd',
            {'token': sepa_direct_debit_token.id},
            auth_as=alice, raise_immediately=False,
        )
        assert r.code == 302, r.text
        r = self.client.GET('/alice/routes/', auth_as=alice)
        assert r.code == 200, r.text
        assert "You have 2 connected payment instruments." in r.text, r.text
        r = self.client.POST(
            '/alice/routes/',
            {'set_as_default': str(offset + 1)},
            auth_as=alice, raise_immediately=False,
        )
        assert r.code == 302, r.text
        r = self.client.POST(
            '/alice/routes/',
            {'remove': str(offset + 1)},
            auth_as=alice, raise_immediately=False,
        )
        assert r.code == 302, r.text
        r = self.client.POST(
            '/alice/routes/',
            {'remove': str(offset)},
            auth_as=alice, raise_immediately=False,
        )
        assert r.code == 302, r.text
        routes = self.db.all("SELECT r FROM exchange_routes r WHERE r.status = 'chargeable'")
        assert not routes
