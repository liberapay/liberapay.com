import fnmatch
import os
import posixpath
import re
from urllib.parse import urlsplit

import dartsass as sass
from aspen import renderers

from ..website import website


class Renderer(renderers.Renderer):

    def __init__(self, factory, *a, **kw):
        self.request_processor = factory._configuration
        renderers.Renderer.__init__(self, factory, *a, **kw)
        self.cache_static = website.env.cache_static
        compress = website.env.compress_assets
        output_style = 'compressed' if compress else 'expanded'
        kw = dict(output_style=output_style)
        if self.request_processor.project_root is not None:
            kw['load_paths'] = self.request_processor.project_root
        self.sass_conf = kw

    # SASS doesn't support wildcard imports, so we implement it ourselves
    wildcard_import_re = re.compile(r'@import "(.*/)\*"')

    def wildcard_import_sub(self, m):
        d = m.group(1)
        files = sorted(os.listdir(self.request_processor.project_root + '/' + d))
        files = fnmatch.filter(files, '*.scss')
        return '; '.join('@import "%s"' % (d + name[:-5]) for name in files)

    def compile(self, filepath, src):
        basepath = posixpath.dirname(filepath) + '/'
        assets_root = self.request_processor.www_root + '/assets/'
        if basepath.startswith(assets_root):
            basepath = basepath[len(assets_root):]
        self.basepath = (basepath.rstrip('/') + '/').lstrip('/')
        return self.wildcard_import_re.sub(self.wildcard_import_sub, src)

    url_re = re.compile(r"""\burl\((['"])(.+?)['"]\)""")

    def url_sub(self, m):
        url = urlsplit(m.group(2))
        if url.scheme or url.netloc:
            # We need both tests because "//example.com" has no scheme and "data:"
            # has no netloc. In either case, we want to leave the URL untouched.
            return m.group(0)
        path = posixpath.normpath(self.basepath + url.path)
        repl = website.asset(path) \
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
