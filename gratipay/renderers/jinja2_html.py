import aspen_jinja2_renderer as base

from markupsafe import escape as htmlescape


class HTMLRenderer(base.Renderer):
    def render_content(self, context):
        # Extend to inject HTML-escaping i18n functions.
        _, ngettext = context['_'], context['ngettext']
        context['_'] = lambda *a, **kw: _(*a, **dict(kw, escape=htmlescape))
        context['ngettext'] = lambda *a, **kw: ngettext(*a, **dict(kw, escape=htmlescape))
        return base.Renderer.render_content(self, context)


class Factory(base.Factory):

    Renderer = HTMLRenderer

    def compile_meta(self, configuration):
        # Override to turn on autoescaping.
        loader = base.FileSystemLoader(configuration.project_root)
        return base.Environment( loader=loader
                               , autoescape=True
                               , extensions=['jinja2.ext.autoescape']
                                )
