#!/usr/bin/env python

from __future__ import print_function

import os
import sys
import glob
import shutil
from fabricate import autoclean, main, shell
from fabricate import run as fab_run

if sys.platform.startswith('win'):
    BIN = ['env', 'Scripts']
else:
    BIN = ['env', 'bin']


PIP = os.path.join(*(BIN + ['pip']))
SWADDLE = os.path.join(*(BIN + ['swaddle']))
ASPEN = os.path.join(*(BIN + ['aspen']))

p = lambda p: os.path.join(*p.split('/'))
LOCAL_ENV = p('./local.env')
DEFAULT_LOCAL_ENV = p('./default_local.env')


def remove_path(*args):
    globbed = []
    for path in args:
        globbed.extend(glob.glob(path))

    for path in globbed:
        if os.path.isdir(path):
            shutil.rmtree(path)
        elif os.path.isfile(path):
            os.remove(path)


def remove_path_recursive(root, *args):
    for _, dirs, _ in os.walk(root):
        for name in dirs:
            remove_path(*[os.path.join(name, path) for path in args])


def pip_install(*a):
    fab_run(PIP, 'install', *a)


def build():
    env()


def env():
    if not shell('python', '--version').startswith('Python 2.7'):
        raise SystemExit('Error: Python 2.7 required')

    fab_run('python', './vendor/virtualenv-1.7.1.2.py',
            '--unzip-setuptools',
            '--prompt="[gittip] "',
            '--never-download',
            '--extra-search-dir=' + p('./vendor/'),
            '--distribute',
            p('./env/'))

    pip_install('-r', p('./requirements.txt'))
    pip_install(p('./vendor/nose-1.1.2.tar.gz'))
    pip_install('-e', p('./'))


def clean():
    remove_path('env', '*.egg', '*.egg-info', p('tests/env'))
    remove_path_recursive(p('./'), '*.pyc')
    autoclean()


def local_env():
    if os.path.exists(LOCAL_ENV):
        return

    print('Creating a local.env file...\n')
    shutil.copyfile(DEFAULT_LOCAL_ENV, LOCAL_ENV)


def serve():
    run()


def run():
    env()
    local_env()

    try:
        fab_run(SWADDLE, LOCAL_ENV, ASPEN,
                '--www_root=www' + os.sep,
                '--project_root=.',
                '--show_tracebacks=yes',
                '--changes_reload=yes',
                '--network_address=:8537')
    except KeyboardInterrupt:
        pass


"""
test: env tests/env data
    ./env/Scripts/swaddle tests/env ./env/Scripts/nosetests ./tests/

tests: test

tests/env:
    echo "Creating a tests/env file ..."
    echo
    cp default_tests.env tests/env

data: env
    ./makedb.sh gittip-test gittip-test
    ./env/Scripts/swaddle tests/env ./env/Scripts/python ./gittip/testing/__init__.py
"""


main(default='env')
