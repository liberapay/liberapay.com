#!/usr/bin/env python

"""
This module holds our gunicorn settings and launcher.

Docs: http://docs.gunicorn.org/en/stable/settings.html
"""

from os import environ as env, execlp

_canonical_host = env['CANONICAL_HOST']
_production = _canonical_host == 'liberapay.com'

if __name__ == '__main__':
    # Exec gunicorn, ask it to read its settings from this file
    program = 'gunicorn'
    execlp(program, program, 'liberapay.main:website', '--config', 'app.py')

accesslog = '-'  # stderr
access_log_format = (
    '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "-" %(L)ss'
)

bind = [
    env['OPENSHIFT_PYTHON_IP'] + ':' + env['OPENSHIFT_PYTHON_PORT']
    if _production else
    _canonical_host
]

chdir = env['OPENSHIFT_REPO_DIR'] if _production else ''

if _production:
    pid_file = env['OPENSHIFT_DATA_DIR'] + '/gunicorn.pid'

# Import extra settings from the GUNICORN_OPTS env var
import shlex
globals().update(
    s.split('=', 1) for s in shlex.split(env.get('GUNICORN_OPTS'))
)
