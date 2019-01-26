# coding: utf8

from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from datetime import timedelta

from markupsafe import escape
from pando.http.response import Response

from liberapay import utils
from liberapay.testing import Harness
from liberapay.utils import markdown, b64encode_s, b64decode_s
from liberapay.wireup import CSP


class Tests(Harness):

    # get_participant
    # ===============

    def test_get_participant_gets_participant(self):
        expected = self.make_participant('alice')
        state = self.client.GET('/alice/', return_after='handle_dispatch_exception',
                                want='state')
        actual = utils.get_participant(state, restrict=False)
        assert actual == expected

    def test_get_participant_gets_participant_from_id(self):
        expected = self.make_participant('alice')
        state = self.client.POST('/~1/', return_after='handle_dispatch_exception',
                                 want='state')
        actual = utils.get_participant(state, restrict=False)
        assert actual == expected

    def GxT(self, path):
        state = self.client.GET(path, return_after='handle_dispatch_exception',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        return cm.exception

    def test_get_participant_raises_404_for_missing_id(self):
        r = self.GxT('/~/')
        assert r.code == 404

    def test_get_participant_canonicalizes(self):
        self.make_participant('alice')
        r = self.GxT('/Alice/?foo=bar')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/?foo=bar'

    def test_get_participant_canonicalizes_id_to_username(self):
        self.make_participant('alice')
        r = self.GxT('/~1/?x=2')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/?x=2'

    def test_get_participant_redirects_after_username_change(self):
        p = self.make_participant(None)
        p.change_username('alice')
        # 1st username change
        self.db.run("UPDATE events SET ts = ts - interval '30 days'")
        p.change_username('bob')
        r = self.GxT('/alice')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/bob'
        # 2nd username change
        self.db.run("UPDATE events SET ts = ts - interval '30 days'")
        p.change_username('carl')
        r = self.GxT('/alice')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/carl'
        r = self.GxT('/bob')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/carl'
        # 3rd username change: back to the original
        self.db.run("UPDATE events SET ts = ts - interval '30 days'")
        p.change_username('alice')
        r = self.client.GET('/alice')
        assert r.code == 200
        r = self.GxT('/bob')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice'
        r = self.GxT('/carl')
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice'

    # Card expiration
    # ===============

    def test_is_expired(self):
        expiration = datetime.utcnow() - timedelta(days=40)
        assert utils.is_card_expired(expiration.year, expiration.month)

    def test_not_expired(self):
        expiration = datetime.utcnow() + timedelta(days=100)
        assert not utils.is_card_expired(expiration.year, expiration.month)

    # Markdown
    # ========

    def test_markdown_render_does_render(self):
        expected = "<p>Example</p>\n"
        actual = markdown.render('Example')
        assert expected == actual

    def test_markdown_render_discards_scripts(self):
        expected = '<p>Example alert(1);</p>\n'
        actual = markdown.render('Example <script>alert(1);</script>')
        assert expected == actual
        payload = '<sc<script>ript>alert(123)</sc</script>ript>'
        html = markdown.render(payload)
        assert '<script>' not in html

    def test_markdown_autolink_filtering(self):
        # Nice data
        for url in ('http://a', "https://b?x&y", 'xmpp:c'):
            expected = '<p><a href="{0}">{0}</a></p>\n'.format(escape(url))
            actual = markdown.render('<%s>' % url)
            assert actual == expected
        # Naughty data
        expected = '<p>&lt;javascript:foo&gt;</p>\n'
        assert markdown.render('<javascript:foo>') == expected
        link = 'javascript:0'
        encoded_link = ''.join('&x{0:x};'.format(ord(c)) for c in link)
        html = markdown.render('<%s>' % encoded_link)
        assert link not in html

    def test_markdown_link_filtering(self):
        # Nice data
        for url in ('http://a', 'https://b', 'xmpp:c'):
            expected = '<p><a href="{0}" title="bar&#39;">&#39;foo</a></p>\n'.format(url)
            actual = markdown.render("['foo](%s \"bar'\")" % url)
            assert actual == expected
        # Naughty data
        html = markdown.render('[foo](javascript:xss)')
        assert html == '<p>[foo](javascript:xss)</p>\n'
        html = markdown.render('[foo](unknown:bar)')
        assert html == '<p>[foo](unknown:bar)</p>\n'
        html = markdown.render('[" xss><xss>]("><xss>)')
        assert '<xss>' not in html
        assert '" xss' not in html
        html = markdown.render('[" xss><xss>](https:"><xss>)')
        assert '<xss>' not in html
        assert '" xss' not in html

    def test_markdown_image_src_filtering(self):
        # Nice data
        expected = '<p><img src="http:&#34;foo&#34;" /></p>\n'
        assert markdown.render('![](http:"foo")') == expected
        expected = '<p><img src="https://example.org/" alt="&#34;bar&#34;" title="&#39;title&#39;" /></p>\n'
        assert markdown.render('!["bar"](https://example.org/ "\'title\'")') == expected
        # Naughty data
        expected = '<p>![foo](javascript:foo)</p>\n'
        assert markdown.render('![foo](javascript:foo)') == expected

    def test_markdown_render_doesnt_allow_any_explicit_anchors(self):
        expected = '<p>foo</p>\n'
        assert markdown.render('<a href="http://example.com/">foo</a>') == expected
        expected = '<p>foo</p>\n'
        assert markdown.render('<a href="https://example.com/">foo</a>') == expected
        expected = '<p>foo</p>\n'
        assert markdown.render('<a href="javascript:foo">foo</a>') == expected

    def test_markdown_render_autolinks(self):
        expected = '<p><a href="http://google.com/">http://google.com/</a></p>\n'
        actual = markdown.render('http://google.com/')
        assert expected == actual

    def test_markdown_render_no_intra_emphasis(self):
        expected = '<p>Examples like this_one and this other_one.</p>\n'
        actual = markdown.render('Examples like this_one and this other_one.')
        assert expected == actual

    # Base64 encoding/decoding
    # ========================

    def test_safe_base64_transcode_works_with_binary_data(self):
        utils.b64decode_s(utils.b64encode_s(b'\xff'))

    def test_b64encode_s_replaces_slash_with_underscore(self):
        # TheEnter?prise => VGhlRW50ZXI/cHJpc2U=
        assert b64encode_s('TheEnter?prise') == 'VGhlRW50ZXI_cHJpc2U~'

    def test_b64encode_s_replaces_equals_with_tilde(self):
        assert b64encode_s('TheEnterprise') == 'VGhlRW50ZXJwcmlzZQ~~'

    def test_b64decode_s_decodes(self):
        assert b64decode_s('VGhlRW50ZXI_cHJpc2U~') == 'TheEnter?prise'

    def test_b64decode_s_raises_response_on_error(self):
        with self.assertRaises(Response) as cm:
            b64decode_s('abcd')
        assert cm.exception.code == 400

    def test_b64decode_s_returns_default_if_passed_on_error(self):
        assert b64decode_s('abcd', default='error') == 'error'

    # CSP
    # ===

    def test_csp_handles_valueless_directives_correctly(self):
        csp = b"default-src 'self';upgrade-insecure-requests;"
        csp2 = CSP(csp)
        assert csp == csp2
        assert csp2.directives[b'upgrade-insecure-requests'] == b''
