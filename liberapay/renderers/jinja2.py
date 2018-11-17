import aspen_jinja2_renderer as base

from markupsafe import escape as htmlescape

from liberapay.website import JINJA_ENV_COMMON


class Renderer(base.Renderer):

    autoescape = True

    def render_content(self, context):
        # Extend to inject an HTML-escaping function. Since autoescape is on,
        # template authors shouldn't normally need to use this function, but
        # having it in the simplate context makes it easier to implement i18n.
        if self.is_sgml:
            context['escape'] = context['state']['escape'] = htmlescape
        return base.Renderer.render_content(self, context)


class Factory(base.Factory):

    Renderer = Renderer

    def compile_meta(self, configuration):
        # Override to add our own JINJA_ENV_COMMON conf
        loader = base.FileSystemLoader(configuration.project_root)
        return {
            'default_env': base.Environment(loader=loader, **JINJA_ENV_COMMON),
            'htmlescaped_env': base.Environment(
                loader=loader,
                autoescape=True,
                **JINJA_ENV_COMMON
            ),
        }
