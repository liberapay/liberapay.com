"""This subpackage contains functionality for working with accounts elsewhere.
"""
from __future__ import print_function, unicode_literals

from aspen.utils import typecheck
from aspen.http.request import UnicodeWithParams
from gittip.models.participant import reserve_a_random_username
from gittip.models.account_elsewhere import AccountElsewhere
from psycopg2 import IntegrityError


ACTIONS = ['opt-in', 'connect', 'lock', 'unlock']


# Exceptions
# ==========

class UnknownAccountElsewhere(Exception):
    pass

class BadAccountElsewhereSubclass(Exception):
    def __str__(self):
        return "The Platform subclass {} specifies an account_elsewhere_subclass that " \
               "doesn't subclass AccountElsewhere.".format(self.args[0])

class MissingAttributes(Exception):
    def __str__(self):
        return "The Platform subclass {} is missing: {}."\
                .format(self.args[0], ', '.join(self.args[1]))


# Platform Objects
# ================

class PlatformRegistry(object):
    """Registry of platforms we support connecting to your Gittip account.
    """

    def __init__(self, db):
        self.db = db

    def get(self, name, default=None):
        return getattr(self, name, default)

    def __getitem__(self, name):
        platform = self.get(name)
        if platform is None:
            raise KeyError(name)
        return platform

    def register(self, *Platforms):
        for Platform in Platforms:
            platform = Platform(self.db)
            self.__dict__[platform.name] = platform
            AccountElsewhere.subclasses[platform.name] = platform.account_elsewhere_subclass


class Platform(object):

    def __init__(self, db):
        self.db = db


        # Make sure the subclass was implemented properly.
        # ================================================

        expected_attrs = ( 'account_elsewhere_subclass'
                         , 'hit_api'
                         , 'name'
                         , 'username_key'
                         , 'user_id_key'
                          )
        missing_attrs = []
        for attr in expected_attrs:
            if not hasattr(self, attr):
                missing_attrs.append(attr)
        if missing_attrs:
            raise MissingAttributes(self.__class__.__name__, missing_attrs)

        if not issubclass(self.account_elsewhere_subclass, AccountElsewhere):
            raise BadAccountElsewhereSubclass(self.account_elsewhere_subclass)


    def get_account(self, username):
        """Given a username on the other platform, return an AccountElsewhere object.
        """
        typecheck(username, UnicodeWithParams)
        try:
            out = self.fetch_from_db(username)
        except UnknownAccountElsewhere:
            out = self.fetch_from_api(username)
        return out


    def fetch_from_db(self, username):
        """Given a username on the other platform, return an AccountElsewhere object.

        If the account elsewhere is unknown to us, we raise UnknownAccountElsewhere.

        """
        return self.db.one("""

            SELECT elsewhere.*::elsewhere_with_participant
              FROM elsewhere
             WHERE platform=%s
               AND user_info->%s = %s

        """, (self.name, self.username_key, username), default=UnknownAccountElsewhere)


    def fetch_from_api(self, username):
        """Given a username on the other platform, return an AccountElsewhere object.
        """
        user_id, user_info = self._fetch_from_api(username)
        return self.upsert(user_id, user_info)


    def _fetch_from_api(self, username):
        # Factored out so we can call upsert without hitting API for testing.
        user_info = self.hit_api(username)
        user_id = unicode(user_info[self.user_id_key])  # If this is KeyError, then what?
        return user_id, user_info


    def upsert(self, user_id, user_info):
        """Given a string and a dict, dance with our db and return an AccountElsewhere.
        """
        typecheck(user_id, unicode, user_info, dict)


        # Insert the account if needed.
        # =============================
        # Do this with a transaction so that if the insert fails, the
        # participant we reserved for them is rolled back as well.

        try:
            with self.db.get_cursor() as cursor:
                random_username = reserve_a_random_username(cursor)
                cursor.execute( "INSERT INTO elsewhere "
                                "(platform, user_id, participant) "
                                "VALUES (%s, %s, %s)"
                              , (self.name, user_id, random_username)
                               )
        except IntegrityError:

            # We have a db-level uniqueness constraint on (platform, user_id)

            pass


        # Update their user_info.
        # =======================
        # Cast everything to unicode, because (I believe) hstore can take any
        # type of value, but psycopg2 can't.
        #
        #   https://postgres.heroku.com/blog/past/2012/3/14/introducing_keyvalue_data_storage_in_heroku_postgres/
        #   http://initd.org/psycopg/docs/extras.html#hstore-data-type
        #
        # XXX This clobbers things, of course, such as booleans. See
        # /on/bitbucket/%username/index.html

        for k, v in user_info.items():
            user_info[k] = unicode(v)


        username = self.db.one("""

            UPDATE elsewhere
               SET user_info=%s
             WHERE platform=%s AND user_id=%s
         RETURNING user_info->%s AS username

        """, (user_info, self.name, user_id, self.username_key))


        # Now delegate to fetch_from_db.
        # ==============================

        return self.fetch_from_db(username)


    def resolve(self, username):
        """Given a username elsewhere, return a username here.
        """
        typecheck(username, unicode)
        participant = self.db.one("""

            SELECT participant
              FROM elsewhere
             WHERE platform=%s
               AND user_info->%s = %s

        """, (self.name, self.username_key, username,))
        # XXX Do we want a uniqueness constraint on $username_key? Can we do that?

        if participant is None:
            raise Exception( "User %s on %s isn't known to us."
                           % (username, self.platform)
                            )
        return participant
