from __future__ import absolute_import, division, print_function, unicode_literals

from ..utils import to_javascript
from . import jinja2_htmlescaped as base


class Renderer(base.Factory.Renderer):

    def render_content(self, context):
        html = super(Renderer, self).render_content(context)
        return 'document.write(%s)' % to_javascript(html)


class Factory(base.Factory):
    Renderer = Renderer
