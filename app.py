#!/usr/bin/env python

import shlex
from os import chdir, environ, execlp

chdir(environ['OPENSHIFT_REPO_DIR'])
program = 'gunicorn'
pid_file = environ['OPENSHIFT_DATA_DIR'] + '/gunicorn.pid'
bind = environ['OPENSHIFT_PYTHON_IP'] + ':' + environ['OPENSHIFT_PYTHON_PORT']
opts = shlex.split(environ.get('GUNICORN_OPTS'))
execlp(
    program, program,
    'liberapay.main:website',
    '--pid', pid_file,
    '--bind', bind,
    *opts
)
