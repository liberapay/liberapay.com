#!/usr/bin/env python
"""Generate *.rst files to mirror *.py files in a Python library.

This script is conceptually similar to the sphinx-apidoc script bundled with
Sphinx:

    http://sphinx-doc.org/man/sphinx-apidoc.html

We produce different *.rst output, however.

"""
from __future__ import print_function, unicode_literals
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
    """Given ../mylib/path/to/package and lists of dir/file names, write rst.
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

    for name in sorted(dirs + files):
        if name in dirs:
            toc(doc_path, name)
        else:
            if not name.endswith('.py'): continue
            if name == '__init__.py': continue

            toc_path = toc(doc_path, name)


            # Write a rst file for each module.
            # =================================

            rst_for_module(toc_path)


def main():
    library_root = os.environ['AUTOLIB_LIBRARY_ROOT']
    for root, dirs, files in os.walk(library_root):
        rst_for_package(root, dirs, files)


if __name__ == '__main__':
    main()
