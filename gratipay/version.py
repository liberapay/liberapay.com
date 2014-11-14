from os.path import abspath, dirname, join

def get_version():
    root = dirname(dirname(abspath(__file__)))
    with open(join(root, 'www/version.txt')) as f:
        version = f.read().strip()
    return version

if __name__ == '__main__':
    print(get_version())
