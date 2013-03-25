#!env/bin/python
import os
import sys
import time

from aspen import server
from subprocess import call, Popen, PIPE


ASPEN_CONF = {
    'www_root': 'www',
    'network_address': ':8537',
    'project_root': '.'
}


def get_server():
    # Configure the environment; Aspen pulls it's config from environment
    # variables so we need to read those from the local.env config file.
    with open('local.env', 'r') as file:
        splitter = '='
        for line in file:
            key, val = line.split(splitter, 1)
            if sys.platform.startswith('win'):
                ctypes.windll.kernel32.SetEnvironmentVariableA(key.strip(),
                        val.strip())
            else:
                os.environ[key.strip()] = val.strip()

    # Run the server.
    cmd_args = ['env/bin/aspen']
    cmd_args = cmd_args + ['--%s=%s' % (k, v) for k, v in ASPEN_CONF.items()]
    proc = Popen(cmd_args, stdout=PIPE, stderr=PIPE)

    # Wait until the server is ready. If we get an Aspen error, throw
    # an exception.
    for line in proc.stdout.readline():
        if 'Oh no! Aspen crashed!' in line or 'Traceback' in line:
            raise Exception('Failed to start server.')

        if 'Starting up Aspen website.' in line:
            print line
            break

    return proc


def run_tests():
    proc = None

    try:
        proc = get_server()
        cmd_args = ['./node_modules/.bin/karma', 'start', 'karma-e2e.conf.js']
        call(cmd_args)
    finally:
        if proc:
            proc.terminate()
            proc.communicate()

if __name__ == '__main__':
    run_tests()
