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
    '%(t)s %(s)s %(L)ss %({Host}i)s "%(r)s" %(b)s "%(f)s"'
)

bind = [
    env['OPENSHIFT_PYTHON_IP'] + ':' + env['OPENSHIFT_PYTHON_PORT']
    if _production else
    _canonical_host
]

chdir = env['OPENSHIFT_REPO_DIR'] if _production else ''

if _production:
    pidfile = env['OPENSHIFT_DATA_DIR'] + '/gunicorn.pid'
