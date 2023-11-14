import sys

if sys.version_info < (3, 12, 0):
    print("Liberapay requires Python >= 3.12, but %s is version %s.%s" %
          (sys.executable, sys.version_info[0], sys.version_info[1]))
    sys.exit(1)
if sys.version_info >= (3, 13, 0):
    print("Warning: Liberapay hasn't been tested with Python >= 3.13, you might encounter bugs.")
