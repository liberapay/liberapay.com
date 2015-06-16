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
        state = self.client.GET( '/alice/'
                               , return_after='dispatch_request_to_filesystem'
                               , want='state'
                                )
        actual = utils.get_participant(state, restrict=False)
        assert actual == expected

    def test_get_participant_canonicalizes(self):
        self.make_participant('alice')
        state = self.client.GET( '/Alice/'
                               , return_after='dispatch_request_to_filesystem'
                               , want='state'
                                )

        with self.assertRaises(Response) as cm:
            utils.get_participant(state, restrict=False)
        actual = cm.exception.code

        assert actual == 302

    def test_dict_to_querystring_converts_dict_to_querystring(self):
        expected = "?foo=bar"
        actual = utils.dict_to_querystring({"foo": ["bar"]})
        assert actual == expected

    def test_dict_to_querystring_converts_empty_dict_to_querystring(self):
        expected = ""
        actual = utils.dict_to_querystring({})
        assert actual == expected

    def test_short_difference_is_expiring(self):
        expiring = datetime.utcnow() + timedelta(days = 1)
        expiring = utils.is_card_expiring(expiring.year, expiring.month)
        assert expiring

    def test_long_difference_not_expiring(self):
        expiring = datetime.utcnow() + timedelta(days = 100)
        expiring = utils.is_card_expiring(expiring.year, expiring.month)
        assert not expiring

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

    def test_markdown_render_autolinks(self):
        expected = '<p><a href="http://google.com/">http://google.com/</a></p>\n'
        actual = markdown.render('http://google.com/')
        assert expected == actual

    def test_markdown_render_no_intra_emphasis(self):
        expected = '<p>Examples like this_one and this other_one.</p>\n'
        actual = markdown.render('Examples like this_one and this other_one.')
        assert expected == actual
