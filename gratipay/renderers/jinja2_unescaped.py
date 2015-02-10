import aspen_jinja2_renderer as base


class UnescapingRenderer(base.Renderer):
    def render_content(self, context):

        # Extend to inject a no-op escaping function. Our i18n machinery
        # depends on this.

        context['escape'] = lambda s: s

        return base.Renderer.render_content(self, context)


class Factory(base.Factory):

    Renderer = UnescapingRenderer
