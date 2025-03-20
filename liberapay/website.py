"""This module instantiates the global `website` object (the equivalent of Flask's `app`).

To avoid circular imports this module should not import any other liberapay submodule.
"""

from contextvars import ContextVar, copy_context
from datetime import timedelta
from functools import cached_property
import logging
import os

from environment import Environment, is_yesish
from markupsafe import Markup
from pando.utils import utcnow
from pando.website import Website as _Website


class Website(_Website):

    state = ContextVar('state')

    @cached_property
    def _html_link(self):
        return Markup('<a href="{}://{}/%s">%s</a>').format(
            self.canonical_scheme, self.canonical_host
        )

    def compute_previous_and_next_payday_dates(self):
        today = utcnow().date()
        days_till_wednesday = (3 - today.isoweekday()) % 7
        last_payday = self.db.one("SELECT max(ts_end)::date FROM paydays")
        if days_till_wednesday == 0 and last_payday == today:
            days_till_wednesday = 7
        next_payday = today + timedelta(days=days_till_wednesday)
        return last_payday, next_payday

    def link(self, path, text):
        return self._html_link % (path, text)

    def read_asset(self, path):
        try:
            assert '..' not in path
            resource = website.request_processor.resources.get(
                f'{website.www_root}/assets/{path}'
            )
            bs = resource.render().body if resource.raw is None else resource.raw
            return bs.decode('utf8')
        except Exception as e:
            self.tell_sentry(e)
            return ''

    def respond(self, *args, **kw):
        # Run in a new (sub)context
        return copy_context().run(super().respond, *args, **kw)

    def tippee_links(self, transfers):
        return [
            self._html_link % ('~%i/' % tr['tippee_id'], tr['tippee_username'])
            for tr in transfers
        ]

    def warning(self, msg):
        self.tell_sentry(Warning(msg))

    def wireup(self, minimal=False):
        from liberapay import wireup
        attributes_before = set(self.__dict__.keys())
        chain = wireup.minimal_chain if minimal else wireup.full_chain
        d = chain.run(**dict(self.__dict__, **self.request_processor.__dict__))
        d.pop('chain', None)
        d.pop('exception', None)
        d.pop('state', None)
        for k, v in d.items():
            if k not in attributes_before:
                self.__dict__[k] = v


env = Environment(
    ASPEN_CHANGES_RELOAD=is_yesish,
    ASPEN_PROJECT_ROOT=str,
    ASPEN_SHOW_TRACEBACKS=is_yesish,
    ASPEN_WWW_ROOT=str,
    AWS_ACCESS_KEY_ID=str,
    AWS_SECRET_ACCESS_KEY=str,
    DATABASE_URL=str,
    DATABASE_MAXCONN=int,
    CANONICAL_HOST=str,
    CANONICAL_SCHEME=str,
    COMPRESS_ASSETS=is_yesish,
    CSP_EXTRA=str,
    HOSTNAME=str,
    TEST_EMAIL_ADDRESS=str,
    SENTRY_DEBUG=is_yesish,
    SENTRY_DSN=str,
    SENTRY_RERAISE=is_yesish,
    LOG_DIR=str,
    KEEP_PAYDAY_LOGS=is_yesish,
    LOGGING_LEVEL=str,
    CACHE_STATIC=is_yesish,
    CLEAN_ASSETS=is_yesish,
    RUN_CRON_JOBS=is_yesish,
    OVERRIDE_PAYDAY_CHECKS=is_yesish,
    OVERRIDE_QUERY_CACHE=is_yesish,
    GRATIPAY_BASE_URL=str,
    SECRET_FOR_GRATIPAY=str,
    INSTANCE_TYPE=str,
)

logging.basicConfig(level=getattr(logging, env.logging_level.upper()))

if env.log_dir[:1] == '$':
    var_name = env.log_dir[1:]
    env.log_dir = os.environ.get(var_name)
    if env.log_dir is None:
        env.missing.append(var_name+' (referenced by LOG_DIR)')

if env.malformed:
    plural = len(env.malformed) != 1 and 's' or ''
    print("=" * 42)
    print("Malformed environment variable%s:" % plural)
    for key, err in env.malformed:
        print("  {} ({})".format(key, err))

if env.missing:
    plural = len(env.missing) != 1 and 's' or ''
    keys = ', '.join([key for key in env.missing])
    print("Missing envvar{}: {}.".format(plural, keys))


website = Website(
    changes_reload=env.aspen_changes_reload,
    project_root=env.aspen_project_root,
    show_tracebacks=env.aspen_show_tracebacks,
    www_root=env.aspen_www_root,
)
website.env = env
website.logger = logging.getLogger('liberapay')
