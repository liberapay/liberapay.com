import re

from markupsafe import Markup
import misaka as m  # http://misaka.61924.nl/


url_re = re.compile(r'^(https?|xmpp):')


class CustomRenderer(m.SaferHtmlRenderer):

    def check_url(self, url, is_image_src=False):
        return bool(url_re.match(url))


renderer = CustomRenderer()
md = m.Markdown(renderer, extensions=(
    'autolink', 'strikethrough', 'no-intra-emphasis', 'tables',
))


def render(markdown):
    return Markup(md(markdown))
