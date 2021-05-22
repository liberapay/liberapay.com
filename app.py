#!/usr/bin/env python

"""
This module holds our gunicorn settings and launcher.

Docs: http://docs.gunicorn.org/en/stable/settings.html
"""

from os import environ as env, execlp
import sys

_canonical_host = env['CANONICAL_HOST']

if __name__ == '__main__':
    # Exec gunicorn, ask it to read its settings from this file
    program = 'gunicorn'
    execlp(program, program, 'liberapay.main:website', '--config', 'app.py', *sys.argv[1:])

accesslog = '-'  # stdout
access_log_format = (
    '%(t)s %(s)s %(L)ss %({Host}i)s "%(r)s" %(b)s "%(f)s"'
) if sys.stdin.isatty() else (
    '%(s)s %(L)s %({Host}i)s "%(r)s" %(b)s "%(f)s"'
)

if ':' in _canonical_host:
    bind = [_canonical_host]
