from functools import wraps

import aspen_jinja2_renderer as base
from jinja2 import Undefined
from markupsafe import escape as htmlescape

from ..i18n.extract import JINJA_BASE_OPTIONS
from ..website import website


def wrap_method(method):
    @wraps(method)
    def f(self, *a, **kw):
        try:
            self._fail_with_undefined_error()
        except Exception as e:
            website.tell_sentry(e, level='warning')
        return method(self, *a, **kw)
    return f


class CustomUndefined(Undefined):
    """This subclass sends errors to Sentry instead of actually raising them.

    Doc: https://jinja.palletsprojects.com/en/2.11.x/api/#undefined-types
    """
    __iter__ = wrap_method(Undefined.__iter__)
    __str__ = wrap_method(Undefined.__str__)
    __len__ = wrap_method(Undefined.__len__)
    __eq__ = wrap_method(Undefined.__eq__)
    __ne__ = wrap_method(Undefined.__ne__)
    __bool__ = wrap_method(Undefined.__bool__)
    __hash__ = wrap_method(Undefined.__hash__)


class DictWithLowercaseFallback(dict):

    def __missing__(self, key):
        return self[key.lower()]


class Environment(base.Environment):

    def __init__(self, **options):
        super().__init__(
            **JINJA_BASE_OPTIONS,
            auto_reload=website.env.aspen_changes_reload,
            undefined=CustomUndefined,
            **options,
        )
        self.tests = DictWithLowercaseFallback(self.tests)


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
        # Override to add our own custom Environment subclass
        loader = base.FileSystemLoader(configuration.project_root)
        return {
            'default_env': Environment(loader=loader),
            'htmlescaped_env': Environment(loader=loader, autoescape=True),
        }
