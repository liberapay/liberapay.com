import argparse
import shlex
import os


p = argparse.ArgumentParser()
p.add_argument(
    '-e', '--env', metavar='file[,file]',
    help="files to read environment variables from")
p.add_argument(
    '-i', '--ignore-environment', default=False, action='store_true',
    help="start with an empty environment")
p.add_argument(
    '-s', '--set', metavar='NAME[=value]', action='append',
    help="a specific environment variable to overwrite")
p.add_argument('cmd', nargs=argparse.REMAINDER)
args = p.parse_args()

env = {} if args.ignore_environment else os.environ
for env_file_path in args.env.split(','):
    try:
        with open(env_file_path, 'r') as f:
            for i, line in enumerate(f):
                line = line.strip()
                if line.startswith('#') or not line:
                    continue
                if line.startswith('export '):
                    line = line[7:].lstrip()
                try:
                    key, value = line.split('=', 1)
                except ValueError:
                    raise SystemExit(f"{env_file_path}:{i}: parsing failed: no `=` found")
                try:
                    value = ' '.join(shlex.split(value, comments=True))
                except ValueError as e:
                    raise SystemExit(f"{env_file_path}:{i}: parsing failed: {e}")
                value = value.replace(r'\n', '\n').replace(r'\t', '\t')
                try:
                    env[key] = value
                except ValueError as e:
                    raise SystemExit(f"{env_file_path}:{i}: setting variable failed: {e}")
    except FileNotFoundError:
        pass

for s in (args.set or ()):
    i = s.find('=')
    if i == -1:
        env.pop(s, None)
    else:
        env[s[:i]] = s[i+1:]

os.execvpe(args.cmd[0], args.cmd, env)
