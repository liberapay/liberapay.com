from __future__ import absolute_import, division, print_function, unicode_literals

import re

from . import jinja2_htmlescaped as base


whitespace_re = re.compile(r'>\s+<')


class Renderer(base.Factory.Renderer):

    def render_content(self, context):
        xml = super(Renderer, self).render_content(context)
        return whitespace_re.sub('><', xml)


class Factory(base.Factory):
    Renderer = Renderer
