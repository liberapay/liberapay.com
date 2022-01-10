"""This module instantiates the global `website` object (the equivalent of Flask's `app`).

To avoid circular imports this module should not import any other liberapay submodule.
"""

from contextvars import ContextVar, copy_context
from functools import wraps
import logging
import os

from cached_property import cached_property
from environment import Environment, is_yesish
from jinja2 import Undefined
from markupsafe import Markup
from pando.website import Website as _Website


class Website(_Website):

    state = ContextVar('state')

    @cached_property
    def _html_link(self):
        return Markup('<a href="{}://{}/%s">%s</a>').format(
            self.canonical_scheme, self.canonical_host
        )

    def link(self, path, text):
        return self._html_link % (path, text)

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


# Common Jinja configuration
# ==========================

def wrap_method(method):
    @wraps(method)
    def f(self, *a, **kw):
        try:
            self._fail_with_undefined_error()
        except Exception as e:
            website.tell_sentry(e, level='warning')
        return method(self, *a, **kw)
    return f


class CustomUndefined(Undefined):
    """This subclass sends errors to Sentry instead of actually raising them.

    Doc: https://jinja.palletsprojects.com/en/2.11.x/api/#undefined-types
    """
    __iter__ = wrap_method(Undefined.__iter__)
    __str__ = wrap_method(Undefined.__str__)
    __len__ = wrap_method(Undefined.__len__)
    __eq__ = wrap_method(Undefined.__eq__)
    __ne__ = wrap_method(Undefined.__ne__)
    __bool__ = wrap_method(Undefined.__bool__)
    __hash__ = wrap_method(Undefined.__hash__)


JINJA_ENV_COMMON = dict(
    trim_blocks=True, lstrip_blocks=True,
    line_statement_prefix='%',
    auto_reload=env.aspen_changes_reload,
    extensions=['jinja2.ext.do'],
    undefined=CustomUndefined,
)
