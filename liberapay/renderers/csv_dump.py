from __future__ import absolute_import, division, print_function, unicode_literals

import csv
from io import BytesIO, StringIO

from six import PY2

from aspen.simplates import renderers


# The python2 version of the csv module doesn't support unicode
codec = 'utf8'


def maybe_encode(s):
    return s.encode(codec) if PY2 else s


class Renderer(renderers.Renderer):

    def render_content(self, context):
        rows = eval(self.compiled, globals(), context)
        if not rows:
            return ''
        if PY2:
            f = BytesIO()
            context['output'].charset = codec
        else:
            f = StringIO()
        w = csv.writer(f)
        if hasattr(rows[0], '_fields'):
            w.writerow(map(maybe_encode, rows[0]._fields))
        w.writerows(rows)
        f.seek(0)
        return f.read()


class Factory(renderers.Factory):
    Renderer = Renderer
