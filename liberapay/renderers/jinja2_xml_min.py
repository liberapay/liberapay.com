import re

from . import jinja2 as base


whitespace_re = re.compile(r'>\s+<')


class Renderer(base.Factory.Renderer):

    def render_content(self, context):
        xml = super(Renderer, self).render_content(context)
        return whitespace_re.sub('><', xml)


class Factory(base.Factory):
    Renderer = Renderer
