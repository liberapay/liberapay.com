#!/usr/bin/env python
from __future__ import print_function
import os


w = lambda f, s, *a, **kw: print(s.format(*a, **kw), file=f)


def rst_for_module(toc_path):
    """Given a toc_path, write rst and return a file object.
    """

    f = open(toc_path + '.rst', 'w+')

    heading = ":mod:`{}`".format(os.path.basename(toc_path))
    dotted = toc_path.replace('/', '.')

    w(f, heading)
    w(f, "=" * len(heading))
    w(f, ".. automodule:: {}", dotted)

    return f


def rst_for_package(root, dirs, files):
    """Given ../gittip/path/to/package and lists of dir/file names, write rst.
    """

    doc_path = root[3:]
    if not os.path.isdir(doc_path):
        os.mkdir(doc_path)


    # Start a rst doc for this package.
    # =================================

    f = rst_for_module(doc_path)


    # Add a table of contents.
    # ========================

    w(f, ".. toctree::")

    def toc(doc_path, name):
        parent = os.path.dirname(doc_path)
        toc_path = os.path.join(doc_path[len(parent):].lstrip('/'), name)
        if toc_path.endswith('.py'):
            toc_path = toc_path[:-len('.py')]
        w(f, "    {}", toc_path)
        return os.path.join(parent, toc_path)

    for name in sorted(dirs):
        toc(doc_path, name)

    for name in sorted(files):
        if not name.endswith('.py'): continue
        if name == '__init__.py': continue

        toc_path = toc(doc_path, name)


        # Write a rst file for each module.
        # =================================

        rst_for_module(toc_path)


def main():
    for root, dirs, files in os.walk('../gittip'):
        rst_for_package(root, dirs, files)


if __name__ == '__main__':
    main()
