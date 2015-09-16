from __future__ import absolute_import, division, print_function, unicode_literals

import re
from urlparse import urlsplit

import sass
from aspen import renderers


class Renderer(renderers.Renderer):

    def __init__(self, *a, **kw):
        renderers.Renderer.__init__(self, *a, **kw)
        self.website = self._factory._configuration

    url_re = re.compile(r"""\burl\((['"])(.+?)['"]\)""")

    def url_sub(self, m):
        url = urlsplit(m.group(2))
        if url.scheme or url.netloc:
            # We need both tests because "//example.com" has no scheme and "data:"
            # has no netloc. In either case, we want to leave the URL untouched.
            return m.group(0)
        repl = self.website.asset(url.path) \
             + (url.query and '&'+url.query) \
             + (url.fragment and '#'+url.fragment)
        return 'url({0}{1}{0})'.format(m.group(1), repl)

    def replace_urls(self, css):
        return self.url_re.sub(self.url_sub, css)

    def render_content(self, context):
        output_style = 'compressed' if self.website.compress_assets else 'nested'
        kw = dict(output_style=output_style, string=self.compiled)
        if self.website.project_root is not None:
            kw['include_paths'] = self.website.project_root
        css = sass.compile(**kw)
        if self.website.cache_static:
            css = self.replace_urls(css)
        return css

class Factory(renderers.Factory):
    Renderer = Renderer
