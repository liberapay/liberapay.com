from __future__ import absolute_import, division, print_function, unicode_literals

import csv
from io import BytesIO

from aspen import renderers


class Renderer(renderers.Renderer):

    def render_content(self, context):
        rows = eval(self.compiled, globals(), context)
        if not rows:
            return ''
        f = BytesIO()
        w = csv.writer(f)
        if hasattr(rows[0], '_fields'):
            w.writerow(rows[0]._fields)
        w.writerows(rows)
        f.seek(0)
        return f.read()


class Factory(renderers.Factory):
    Renderer = Renderer
