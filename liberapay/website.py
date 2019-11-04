"""This module instantiates the global `website` object (the equivalent of Flask's `app`).

To avoid circular imports this module should not import any other liberapay submodule.
"""

import logging
import os

from environment import Environment, is_yesish
from jinja2 import StrictUndefined
from pando.website import Website


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


# Common Jinja configuration
# ==========================

class CustomUndefined(StrictUndefined):
    __bool__ = __nonzero__ = lambda self: False

    def __str__(self):
        try:
            self._fail_with_undefined_error()
        except Exception as e:
            website.tell_sentry(e, {})
        return ''

    __unicode__ = __str__


JINJA_ENV_COMMON = dict(
    trim_blocks=True, lstrip_blocks=True,
    line_statement_prefix='%',
    auto_reload=env.aspen_changes_reload,
    # undefined=CustomUndefined,
)
