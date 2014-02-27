from __future__ import absolute_import, division, print_function, unicode_literals

from postgres.orm import Model

from gittip.exceptions import ProblemChangingUsername


class AccountElsewhere(Model):

    typname = "elsewhere_with_participant"

    def __init__(self, *args, **kwargs):
        super(AccountElsewhere, self).__init__(*args, **kwargs)
        self.platform_data = getattr(self.platforms, self.platform)

    @property
    def html_url(self):
        return self.platform_data.account_url.format(
            user_id=self.user_id,
            user_name=self.user_name,
            platform_data=self.platform_data
        )

    def opt_in(self, desired_username):
        """Given a desired username, return a User object.
        """
        from gittip.security.user import User
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

    def set_is_locked(self, is_locked):
        self.db.run("""

            UPDATE elsewhere
               SET is_locked=%s
             WHERE platform=%s AND user_id=%s

        """, (is_locked, self.platform, self.user_id))
