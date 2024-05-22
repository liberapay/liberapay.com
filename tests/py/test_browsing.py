import os
import re

from pando import Response
import pytest

from liberapay.billing.payday import Payday
from liberapay.testing import EUR, Harness
from liberapay.utils import find_files


overescaping_re = re.compile(r'&amp;(#[0-9]+|#x[0-9a-f]+|[a-z0-9]+);')


class BrowseTestHarness(Harness):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        i = len(cls.client.www_root)
        def f(spt):
            if spt[spt.rfind('/')+1:].startswith('index.'):
                return spt[i:spt.rfind('/')+1]
            return spt[i:-4]
        urls = {}
        for url in sorted(map(f, find_files(cls.client.www_root, '*.spt'))):
            url = url.replace('/%username/membership/', '/team/membership/') \
                     .replace('/team/membership/%action', '/team/membership/join') \
                     .replace('/%username/news/%action', '/%username/news/subscribe') \
                     .replace('/for/%name/', '/for/wonderland/') \
                     .replace('/for/wonderland/%action', '/for/wonderland/leave') \
                     .replace('/%platform', '/github') \
                     .replace('/%user_name/', '/liberapay/') \
                     .replace('/%redirect_to', '/giving') \
                     .replace('/%back_to', '/') \
                     .replace('/%provider', '/stripe') \
                     .replace('/%payment_id', '/') \
                     .replace('/%payin_id', '/') \
                     .replace('/payday/%id', '/payday/') \
                     .replace('/%type', '/receiving.js')
            urls[url.replace('/%username/', '/david/')] = None
            urls[url.replace('/%username/', '/team/')] = None
        cls.urls = list(urls)

    def browse_setup(self):
        self.david = self.make_participant('david')
        self.team = self.make_participant('team', kind='group')
        c = self.david.create_community('Wonderland')
        self.david.upsert_community_membership(True, c.id)
        self.team.add_member(self.david)
        self.org = self.make_participant('org', kind='organization')
        self.invoice_id = self.db.one("""
            INSERT INTO invoices
                        (sender, addressee, nature, amount, description, details, documents, status)
                 VALUES (%s, %s, 'expense', ('28.04','EUR'), 'badges and stickers', null, '{}'::jsonb, 'new')
              RETURNING id
        """, (self.david.id, self.org.id))
        self.route = self.db.ExchangeRoute.upsert_generic_route(self.david, 'paypal')
        Payday.start().run()

    def browse(self, **kw):
        for url in self.urls:
            if url.endswith('/%exchange_id') or '/receipts/' in url:
                continue
            if '/%route_id' in url:
                url = url.replace('/%route_id', f'/{self.route.id}')
            url = url.replace('/team/invoices/%invoice_id', '/org/invoices/%s' % self.invoice_id)
            url = url.replace('/%invoice_id', '/%s' % self.invoice_id)
            assert '/%' not in url
            try:
                r = self.client.GET(url, **kw)
            except Response as e:
                if e.code == 404 or e.code >= 500:
                    raise
                r = e
            assert r.code != 404
            assert r.code < 500
            assert not overescaping_re.search(r.text)


class TestBrowsing(BrowseTestHarness):

    def test_anon_can_browse_in_french(self):
        self.browse_setup()
        self.browse(HTTP_ACCEPT_LANGUAGE=b'fr')

    def test_new_participant_can_browse(self):
        self.browse_setup()
        self.browse(auth_as=self.david)

    def test_active_participant_can_browse(self):
        self.browse_setup()
        self.add_payment_account(self.david, 'stripe')
        bob = self.make_participant('bob')
        self.add_payment_account(bob, 'paypal')
        bob.set_tip_to(self.david, EUR('1.00'))
        bob_card = self.upsert_route(bob, 'stripe-card')
        self.make_payin_and_transfer(bob_card, self.david, EUR('2.00'))
        self.david.set_tip_to(bob, EUR('0.50'))
        david_paypal = self.upsert_route(self.david, 'paypal')
        self.make_payin_and_transfer(david_paypal, bob, EUR('20.00'))
        self.browse(auth_as=self.david)

    def test_admin_can_browse(self):
        self.browse_setup()
        admin = self.make_participant('admin', privileges=1)
        self.browse(auth_as=admin)


@pytest.mark.skipif(
    os.environ.get('LIBERAPAY_I18N_TEST') != 'yes',
    reason="this is an expensive test, we don't want to run it every time",
)
class TestTranslations(BrowseTestHarness):

    def test_all_pages_in_all_supported_langs(self):
        self.browse_setup()
        for _, l in self.client.website.lang_list:
            self.browse(HTTP_ACCEPT_LANGUAGE=l.tag.encode('ascii'))
