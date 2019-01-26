from ..utils import to_javascript
from . import jinja2 as base


class Renderer(base.Factory.Renderer):

    def render_content(self, context):
        content = super(Renderer, self).render_content(context)
        return 'document.write(%s)' % to_javascript(content)


class Factory(base.Factory):
    Renderer = Renderer
