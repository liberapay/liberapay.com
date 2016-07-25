from __future__ import absolute_import, division, print_function, unicode_literals

import re
from urlparse import urlsplit

import sass
from aspen import renderers


class Renderer(renderers.Renderer):

    def __init__(self, *a, **kw):
        renderers.Renderer.__init__(self, *a, **kw)
        self.website = self._factory._configuration
        self.cache_static = self.website.env.cache_static
        compress = self.website.app_conf.compress_assets
        output_style = 'compressed' if compress else 'nested'
        kw = dict(output_style=output_style)
        if self.website.project_root is not None:
            kw['include_paths'] = self.website.project_root
        self.sass_conf = kw

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
        css = sass.compile(**dict(self.sass_conf, string=self.compiled))
        if self.cache_static:
            css = self.replace_urls(css)
        return css

class Factory(renderers.Factory):
    Renderer = Renderer
