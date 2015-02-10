import aspen_jinja2_renderer as base

from markupsafe import escape as htmlescape


class HTMLRenderer(base.Renderer):
    def render_content(self, context):

        # Extend to inject an HTML-escaping function. Since autoescape is on,
        # template authors shouldn't normally need to use this function, but
        # having it in the simplate context makes it easier to implement i18n.

        context['escape'] = context['request'].context['escape'] = htmlescape

        # ^^^ Yes, this is fugly. We need the escaping function in the
        # request.context dictionary because that's where the i18n functions
        # look for it, and we need it in `context` (which is a Jinja2 context,
        # which is not identical with request.context) so that it's properly
        # available inside of simplate pages 3+.

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
