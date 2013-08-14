import os
from aspen.utils import typecheck


class UnknownPlatform(Exception): pass


class MixinElsewhere(object):
    """We use this as a mixin for Participant, and in a hackish way on the
    homepage and community pages.

    """

    def get_accounts_elsewhere(self):
        """Return a four-tuple of elsewhere Records.
        """
        github_account = None
        twitter_account = None
        bitbucket_account = None
        bountysource_account = None

        ACCOUNTS = "SELECT * FROM elsewhere WHERE participant=%s"
        accounts = self.db.all(ACCOUNTS, (self.username,))

        for account in accounts:
            if account.platform == "github":
                github_account = account
            elif account.platform == "twitter":
                twitter_account = account
            elif account.platform == "bitbucket":
                bitbucket_account = account
            elif account.platform == "bountysource":
                bountysource_account = account
            else:
                raise UnknownPlatform(account.platform)

        return ( github_account
               , twitter_account
               , bitbucket_account
               , bountysource_account
                )


    def get_img_src(self, size=128):
        """Return a value for <img src="..." />.

        Until we have our own profile pics, delegate. XXX Is this an attack
        vector? Can someone inject this value? Don't think so, but if you make
        it happen, let me know, eh? Thanks. :)

            https://www.gittip.com/security.txt

        """
        typecheck(size, int)

        src = '/assets/%s/avatar-default.gif' % os.environ['__VERSION__']

        github, twitter, bitbucket, bountysource = \
                                                  self.get_accounts_elsewhere()
        if github is not None:
            # GitHub -> Gravatar: http://en.gravatar.com/site/implement/images/
            if 'gravatar_id' in github.user_info:
                gravatar_hash = github.user_info['gravatar_id']
                src = "https://www.gravatar.com/avatar/%s.jpg?s=%s"
                src %= (gravatar_hash, size)

        elif twitter is not None:
            # https://dev.twitter.com/docs/api/1.1/get/users/show
            if 'profile_image_url_https' in twitter.user_info:
                src = twitter.user_info['profile_image_url_https']

                # For Twitter, we don't have good control over size. The
                # biggest option is 73px(?!), but that's too small. Let's go
                # with the original: even though it may be huge, that's
                # preferrable to guaranteed blurriness. :-/

                src = src.replace('_normal.', '.')

        return src
