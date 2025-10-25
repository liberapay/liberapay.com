import csv
from io import StringIO

from aspen.simplates import renderers


class Renderer(renderers.Renderer):

    def render_content(self, context):
        rows = eval(self.compiled, globals(), context)
        if not rows:
            return ''
        f = StringIO()
        if hasattr(rows[0], '_fields'):
            w = csv.writer(f)
            w.writerow(rows[0]._fields)
        elif isinstance(rows[0], dict):
            w = csv.DictWriter(f, rows[0].keys())
            w.writeheader()
        else:
            raise TypeError(type(rows[0]))
        w.writerows(rows)
        f.seek(0)
        return f.read()


class Factory(renderers.Factory):
    Renderer = Renderer
