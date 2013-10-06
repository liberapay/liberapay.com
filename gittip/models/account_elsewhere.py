from __future__ import absolute_import, division, print_function, unicode_literals

from gittip.models.participant import ProblemChangingUsername
from gittip.security.user import User
from postgres.orm import Model


class UnknownPlatform(Exception):
    def __str__(self):
        return "Unknown platform for account elsewhere: {}.".format(self.args[0])


class AccountElsewhere(Model):

    typname = "elsewhere_with_participant"
    subclasses = {}  # populated in gittip.wireup.elsewhere


    def __new__(cls, record):
        platform = record['platform']
        cls = cls.subclasses.get(platform)
        if cls is None:
            raise UnknownPlatform(platform)
        obj = super(AccountElsewhere, cls).__new__(cls, record)
        return obj


    def set_is_locked(self, is_locked):
        self.db.run("""

            UPDATE elsewhere
               SET is_locked=%s
             WHERE platform=%s AND user_id=%s

        """, (is_locked, self.platform, self.user_id))


    def opt_in(self, desired_username):
        """Given a desired username, return a User object.
        """
        self.set_is_locked(False)
        user = User.from_username(self.participant.username)
        user.sign_in()
        assert not user.ANON, self.participant  # sanity check
        if self.participant.is_claimed:
            newly_claimed = False
        else:
            newly_claimed = True
            user.participant.set_as_claimed()
            try:
                user.participant.change_username(desired_username)
            except ProblemChangingUsername:
                pass
        return user, newly_claimed
