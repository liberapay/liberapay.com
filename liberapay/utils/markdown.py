import re

from markupsafe import Markup
import misaka as m  # http://misaka.61924.nl/


uri_re = re.compile(r'^(https?|xmpp|imap|irc|nntp):')


class CustomRenderer(m.SaferHtmlRenderer):

    def check_url(self, url, is_image_src=False):
        return bool(uri_re.match(url))


renderer = CustomRenderer()
md = m.Markdown(renderer, extensions=(
    'autolink', 'strikethrough', 'no-intra-emphasis', 'tables',
))


def render(markdown):
    return Markup(md(markdown))
