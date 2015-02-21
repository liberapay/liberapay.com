from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from datetime import timedelta

import pytest
from aspen.http.response import Response
from gratipay import utils
from gratipay.testing import Harness
from gratipay.utils import i18n, markdown
from gratipay.utils.username import safely_reserve_a_username, FailedToReserveUsername, \
                                                                           RanOutOfUsernameAttempts
from psycopg2 import IntegrityError


class Tests(Harness):

    def test_get_participant_gets_participant(self):
        expected = self.make_participant('alice', claimed_time='now')
        request = self.client.GET( '/alice/'
                                 , return_after='dispatch_request_to_filesystem'
                                 , want='request'
                                  )
        actual = utils.get_participant(request, restrict=False)
        assert actual == expected

    def test_get_participant_canonicalizes(self):
        self.make_participant('alice', claimed_time='now')
        request = self.client.GET( '/Alice/'
                                 , return_after='dispatch_request_to_filesystem'
                                 , want='request'
                                  )

        with self.assertRaises(Response) as cm:
            utils.get_participant(request, restrict=False)
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
        actual = i18n.format_currency_with_options(16, 'USD', locale='en', trailing_zeroes=False)
        assert actual == expected

    def test_format_currency_with_trailing_zeroes(self):
        expected = '$16.00'
        actual = i18n.format_currency_with_options(16, 'USD', locale='en', trailing_zeroes=True)
        assert actual == expected

    def test_format_currency_defaults_to_trailing_zeroes(self):
        expected = '$16.00'
        actual = i18n.format_currency_with_options(16, 'USD', locale='en')
        assert actual == expected


    # sru - safely_reserve_a_username

    def test_srau_safely_reserves_a_username(self):
        def gen_test_username():
            yield 'deadbeef'
        def reserve(cursor, username):
            return 'deadbeef'
        with self.db.get_cursor() as cursor:
            username = safely_reserve_a_username(cursor, gen_test_username, reserve)
        assert username == 'deadbeef'
        assert self.db.one('SELECT username FROM participants') is None

    def test_srau_inserts_a_participant_by_default(self):
        def gen_test_username():
            yield 'deadbeef'
        with self.db.get_cursor() as cursor:
            username = safely_reserve_a_username(cursor, gen_test_username)
        assert username == 'deadbeef'
        assert self.db.one('SELECT username FROM participants') == 'deadbeef'

    def test_srau_wears_a_seatbelt(self):
        def gen_test_username():
            for i in range(101):
                yield 'deadbeef'
        def reserve(cursor, username):
            raise IntegrityError
        with self.db.get_cursor() as cursor:
            with pytest.raises(FailedToReserveUsername):
                safely_reserve_a_username(cursor, gen_test_username, reserve)

    def test_srau_seatbelt_goes_to_100(self):
        def gen_test_username():
            for i in range(100):
                yield 'deadbeef'
        def reserve(cursor, username):
            raise IntegrityError
        with self.db.get_cursor() as cursor:
            with pytest.raises(RanOutOfUsernameAttempts):
                safely_reserve_a_username(cursor, gen_test_username, reserve)

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

    def test_srau_retries_work_with_db(self):
        self.make_participant('deadbeef')
        def gen_test_username():
            yield 'deadbeef'
            yield 'deafbeef'
        with self.db.get_cursor() as cursor:
            username = safely_reserve_a_username(cursor, gen_test_username)
            assert username == 'deafbeef'
