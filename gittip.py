#!/usr/bin/env python
"""\
Gittip
~~~~~~

A personal funding platform.

Dependencies:
- Python 2.7
- Postgresql 9.2

To run:
$ gittip.py

This will also initialize a local environment on the first run.
"""

import os
import sys
import shutil
from subprocess import check_call, check_output, STDOUT, CalledProcessError


is_win = sys.platform.startswith('win')
bin_dir = 'Scripts' if is_win else 'bin'
ext = '.exe' if is_win else ''

default_port = 8537
vendor_path = 'vendor'
env_path = 'env'
requirements_installed_path = os.path.join(env_path, '.requirements_installed')
bin_path = os.path.join(env_path, bin_dir)
default_config_path = 'default_local.env'
config_path = 'local.env'
virtualenv_path = os.path.join(vendor_path, 'virtualenv-1.9.1.py')
pip_path = os.path.join(bin_path, 'pip' + ext)
swaddle_path = os.path.join(bin_path, 'swaddle' + ext)
aspen_path = os.path.join(bin_path, 'aspen' + ext)


def main():
    # TODO: Handle command-line arguments to override default config values
    #  e.g. the address and port to serve on, whether to run tests, etc

    try:
        bootstrap_environment()
    except CalledProcessError as ex:
        print ex.output
    except EnvironmentError as ex:
        print 'Error:', ex
        return 1

    run_server()


def bootstrap_environment():
    ensure_dependencies()
    init_config()
    init_virtualenv()
    install_requirements()


def ensure_dependencies():
    if not shell('python', '--version', capture=True).startswith('Python 2.7'):
        raise EnvironmentError('Python 2.7 is required.')

    try:
        shell('pg_config' + ext, capture=True)
    except OSError as e:
        if e.errno != os.errno.ENOENT:
            raise
        raise EnvironmentError('Postgresql is required. (Make sure pg_config is on your PATH.)')


def init_config():
    if os.path.exists(config_path):
        return

    print 'Creating a %s file...' % config_path
    shutil.copyfile(default_config_path, config_path)


def init_virtualenv():
    if os.path.exists(env_path):
        return

    print 'Initializing virtualenv at %s...' % env_path

    shell('python', virtualenv_path,
          '--unzip-setuptools',
          '--prompt="[gittip] "',
          '--never-download',
          '--extra-search-dir=' + vendor_path,
          '--distribute',
          env_path)


def install_requirements():
    # TODO: Detect when requirements.txt changes instead of checking for a file
    if os.path.exists(requirements_installed_path):
        return

    print 'Installing requirements...'

    shell(pip_path, 'install', '-r', 'requirements.txt')
    shell(pip_path, 'install', os.path.join(vendor_path, 'nose-1.1.2.tar.gz'))
    shell(pip_path, 'install', '-e', '.')

    open(requirements_installed_path, 'w').close()


def run_server():
    # TODO: Wait for Aspen to quit before exiting
    shell(swaddle_path, config_path, aspen_path)


def shell(*args, **kwargs):
    if kwargs.pop('capture', None):
        return check_output(args, stderr=STDOUT, **kwargs)
    return check_call(args, **kwargs)


if __name__ == '__main__':
    sys.exit(main())
