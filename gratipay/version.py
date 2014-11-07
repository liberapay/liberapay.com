from os.path import dirname, isdir, join
from subprocess import CalledProcessError, check_output


def get_version():
    d = dirname(dirname(__file__))

    version = False
    if isdir(join(d, '.git')):
        # Running from source checkout
        cmd = 'git describe --tags --match [0-9]*'.split()
        try:
            version = check_output(cmd).decode().strip()
        except (CalledProcessError, OSError):
            print('Unable to get version number from git tags')

        # PEP 386 compatibility
        if version and '-' in version:
            version = '.post'.join(version.split('-')[:2])

    if not version:
        # [ ] This should really belong to gratipay module
        with open(join(d, 'www/version.txt')) as f:
            version = f.read().strip()

    return version


if __name__ == '__main__':
    print(get_version())
