"""Run a command with an environment specified in a file.
"""
import os
import sys
if sys.platform.startswith('win'):
    import ctypes


def configure(envdef):
    """Given a filepath or -, return a tuple of bytestrings.
    """
    if envdef == '-':               # Heroku-style

        # Heroku used to use =>, which was weird. Now they use :, and we may as
        # well too, but I had already started using =, and now changing would
        # break people's local.env.

        m = "[SWADDLE] reading environment from stdin."
        print >> sys.stderr, m
        fp = sys.stdin
        splitter = ": "
    elif not os.path.isfile(envdef):
        m = "[SWADDLE] %s is not a file; environment unchanged." % envdef
        print >> sys.stderr, m
        envdef = ""
    else:                           # Gittip-style
        fp = open(envdef)
        splitter = "="

    args = sys.argv[2:]
    if not args:
        m ="[SWADDLE] No command specified; exiting."
        raise SystemExit(m)
    if sys.platform == 'win32' and not os.path.isfile(args[0]):
        # Try with an '.exe' extension on Windows if the command doesn't
        # already have an extension.
        if os.path.splitext(args[0])[-1] == '':
            args[0] += '.exe'
    if not os.path.isfile(args[0]):
        m ="[SWADDLE] Command %s does not exist; exiting." % args[0]
        raise SystemExit(m)

    if envdef:
        for line in fp:
            line = line.split('#')[0].strip()
            if splitter not in line:
                m = "[SWADDLE] Skipping line: %s." % line
                print >> sys.stderr, m
                continue
            key, val = line.split(splitter, 1)
            if sys.platform.startswith('win'):
                ctypes.windll.kernel32.SetEnvironmentVariableA(key.strip(), val.strip())
            else:
                os.environ[key.strip()] = val.strip()

    return args


def main():
    if len(sys.argv) < 1:
        m ="[SWADDLE] Usage: %s {definition.env} {command} {args}" % sys.argv[0]
        raise SystemExit(m)
    envdef = sys.argv[1]
    args = configure(envdef)
    os.execv(args[0], args)
