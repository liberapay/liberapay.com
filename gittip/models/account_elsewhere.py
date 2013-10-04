from gittip.models.participant import ProblemChangingUsername
from gittip.security.user import User
from postgres.orm import Model


class AccountElsewhere(Model):

    typname = "elsewhere"


    def get_html_url(self):
        pass


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
        user = User.from_username(self.participant)
        user.sign_in()
        assert not user.ANON, self.participant  # sanity check
        if self.is_claimed:
            newly_claimed = False
        else:
            newly_claimed = True
            user.participant.set_as_claimed()
            try:
                user.participant.change_username(desired_username)
            except ProblemChangingUsername:
                pass
        return user, newly_claimed
