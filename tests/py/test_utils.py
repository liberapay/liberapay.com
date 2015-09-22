from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from datetime import timedelta

from aspen.http.response import Response
from liberapay import utils
from liberapay.testing import Harness
from liberapay.utils import i18n, markdown


class Tests(Harness):

    def test_get_participant_gets_participant(self):
        expected = self.make_participant('alice')
        state = self.client.GET('/alice/', return_after='dispatch_request_to_filesystem',
                                want='state')
        actual = utils.get_participant(state, restrict=False)
        assert actual == expected

    def test_get_participant_gets_participant_from_id(self):
        expected = self.make_participant('alice')
        state = self.client.POST('/~1/', return_after='dispatch_request_to_filesystem',
                                 want='state')
        actual = utils.get_participant(state, restrict=False)
        assert actual == expected

    def test_get_participant_raises_404_for_missing_id(self):
        state = self.client.GET('/~/', return_after='dispatch_request_to_filesystem',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        r = cm.exception
        assert r.code == 404

    def test_get_participant_canonicalizes(self):
        self.make_participant('alice')
        state = self.client.GET('/Alice/?foo=bar', return_after='dispatch_request_to_filesystem',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        r = cm.exception
        assert r.code == 302
        assert r.headers['Location'] == '/alice/?foo=bar'

    def test_get_participant_canonicalizes_id_to_username(self):
        self.make_participant('alice')
        state = self.client.GET('/~1/?x=2', return_after='dispatch_request_to_filesystem',
                                want='state')
        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        r = cm.exception
        assert r.code == 302
        assert r.headers['Location'] == '/alice/?x=2'

    def test_is_expired(self):
        expiration = datetime.utcnow() - timedelta(days = 40)
        assert utils.is_card_expired(expiration.year, expiration.month)

    def test_not_expired(self):
        expiration = datetime.utcnow() + timedelta(days = 100)
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
        expected = '<p>Example alert &ldquo;hi&rdquo;;</p>\n'
        actual = markdown.render('Example <script>alert "hi";</script>')
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
