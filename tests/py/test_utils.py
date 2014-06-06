from __future__ import absolute_import, division, print_function, unicode_literals

from datetime import datetime
from datetime import timedelta

import pytest
from aspen.http.response import Response
from gittip import utils
from gittip.testing import Harness
from gittip.utils.username import safely_reserve_a_username, FailedToReserveUsername, \
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

    def test_linkify_linkifies_url_with_www(self):
        expected = '<a href="http://www.example.com" target="_blank">http://www.example.com</a>'
        actual = utils.linkify('http://www.example.com')
        assert actual == expected

    def test_linkify_linkifies_url_without_www(self):
        expected = '<a href="http://example.com" target="_blank">http://example.com</a>'
        actual = utils.linkify('http://example.com')
        assert actual == expected

    def test_linkify_linkifies_url_with_uppercase_letters(self):
        expected = '<a href="Http://Www.Example.Com" target="_blank">Http://Www.Example.Com</a>'
        actual = utils.linkify('Http://Www.Example.Com')
        assert actual == expected

    def test_linkify_works_without_protocol(self):
        expected = '<a href="http://www.example.com" target="_blank">www.example.com</a>'
        actual = utils.linkify('www.example.com')
        assert actual == expected

    def test_short_difference_is_expiring(self):
        expiring = datetime.utcnow() + timedelta(days = 1)
        expiring = utils.is_card_expiring(expiring.year, expiring.month)
        assert expiring

    def test_long_difference_not_expiring(self):
        expiring = datetime.utcnow() + timedelta(days = 100)
        expiring = utils.is_card_expiring(expiring.year, expiring.month)
        assert not expiring


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

    @pytest.mark.xfail
    def test_srau_retries_work_with_db(self):
        # XXX This is raising InternalError because the transaction is ended or something.
        self.make_participant('deadbeef')
        def gen_test_username():
            yield 'deadbeef'
            yield 'deafbeef'
        with self.db.get_cursor() as cursor:
            username = safely_reserve_a_username(cursor, gen_test_username)
            assert username == 'deafbeef'

    @pytest.mark.xfail
    def test_srau_retries_cheese(self):
        # XXX This is a simplified case of the above test.
        with self.db.get_cursor() as cursor:
            cursor.execute("INSERT INTO participants (username, username_lower) VALUES ('c', 'c')")
            try:
                cursor.execute("INSERT INTO participants (username, username_lower) VALUES ('c', 'c')")
            except:
                pass
            cursor.execute("INSERT INTO participants (username, username_lower) VALUES ('c', 'c')")
