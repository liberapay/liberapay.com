#!/usr/bin/env python

from os import chdir, environ, execlp

chdir(environ['OPENSHIFT_REPO_DIR'])
program = 'gunicorn'
bind = environ['OPENSHIFT_PYTHON_IP'] + ':' + environ['OPENSHIFT_PYTHON_PORT']
execlp(program, program, 'liberapay.main:website', '--bind', bind)
