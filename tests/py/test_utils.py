from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from datetime import timedelta

from pando.http.response import Response

from liberapay import utils
from liberapay.testing import Harness
from liberapay.utils import i18n, markdown, b64encode_s, b64decode_s


class Tests(Harness):

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

    def test_get_participant_raises_404_for_missing_id(self):
        state = self.client.GET('/~/', return_after='handle_dispatch_exception',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        r = cm.exception
        assert r.code == 404

    def test_get_participant_canonicalizes(self):
        self.make_participant('alice')
        state = self.client.GET('/Alice/?foo=bar', return_after='handle_dispatch_exception',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        r = cm.exception
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/?foo=bar'

    def test_get_participant_canonicalizes_id_to_username(self):
        self.make_participant('alice')
        state = self.client.GET('/~1/?x=2', return_after='handle_dispatch_exception',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        r = cm.exception
        assert r.code == 302
        assert r.headers[b'Location'] == b'/alice/?x=2'

    def test_is_expired(self):
        expiration = datetime.utcnow() - timedelta(days=40)
        assert utils.is_card_expired(expiration.year, expiration.month)

    def test_not_expired(self):
        expiration = datetime.utcnow() + timedelta(days=100)
        assert not utils.is_card_expired(expiration.year, expiration.month)

    def test_format_currency_without_trailing_zeroes(self):
        expected = '$16'
        actual = i18n.format_money(16, 'USD', locale='en', trailing_zeroes=False)
        assert actual == expected

    def test_format_currency_defaults_to_trailing_zeroes(self):
        expected = '$16.00'
        actual = i18n.format_money(16, 'USD', locale='en')
        assert actual == expected


    def test_markdown_render_does_render(self):
        expected = "<p>Example</p>\n"
        actual = markdown.render('Example')
        assert expected == actual

    def test_markdown_render_escapes_scripts(self):
        expected = '<p>Example alert(1);</p>\n'
        actual = markdown.render('Example <script>alert(1);</script>')
        assert expected == actual

    def test_markdown_render_renders_http_links(self):
        expected = '<p><a href="http://example.com/">foo</a></p>\n'
        assert markdown.render('[foo](http://example.com/)') == expected
        expected = '<p><a href="http://example.com/">http://example.com/</a></p>\n'
        assert markdown.render('<http://example.com/>') == expected

    def test_markdown_render_renders_https_links(self):
        expected = '<p><a href="https://example.com/">foo</a></p>\n'
        assert markdown.render('[foo](https://example.com/)') == expected
        expected = '<p><a href="https://example.com/">https://example.com/</a></p>\n'
        assert markdown.render('<https://example.com/>') == expected

    def test_markdown_render_renders_xmpp_links(self):
        expected = '<p><a href="xmpp:foo@example.com">foo</a></p>\n'
        assert markdown.render('[foo](xmpp:foo@example.com)') == expected
        expected = '<p><a href="xmpp:foo@example.com">xmpp:foo@example.com</a></p>\n'
        assert markdown.render('<xmpp:foo@example.com>') == expected

    def test_markdown_render_escapes_javascript_links(self):
        expected = '<p>[foo](javascript:foo)</p>\n'
        assert markdown.render('[foo](javascript:foo)') == expected
        expected = '<p>&lt;javascript:foo&gt;</p>\n'
        assert markdown.render('<javascript:foo>') == expected

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
        assert b64encode_s('TheEnter?prise') == str('VGhlRW50ZXI_cHJpc2U~')

    def test_b64encode_s_replaces_equals_with_tilde(self):
        assert b64encode_s('TheEnterprise') == str('VGhlRW50ZXJwcmlzZQ~~')

    def test_b64decode_s_decodes(self):
        assert b64decode_s('VGhlRW50ZXI_cHJpc2U~') == 'TheEnter?prise'

    def test_b64decode_s_raises_response_on_error(self):
        with self.assertRaises(Response) as cm:
            b64decode_s('abcd')
        assert cm.exception.code == 400

    def test_b64decode_s_returns_default_if_passed_on_error(self):
        assert b64decode_s('abcd', default='error') == 'error'
