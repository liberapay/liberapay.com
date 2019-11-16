import re

from markupsafe import Markup, escape
import misaka as m  # http://misaka.61924.nl/


url_re = re.compile(r'^(https?|xmpp):')


class CustomRenderer(m.HtmlRenderer):

    def image(self, link, title='', alt=''):
        if url_re.match(link):
            maybe_alt = Markup(' alt="%s"') % alt if alt else ''
            maybe_title = Markup(' title="%s"') % title if title else ''
            return Markup('<img src="%s"%s%s />') % (link, maybe_alt, maybe_title)
        else:
            return escape("![%s](%s)" % (alt, link))

    def link(self, content, link, title=''):
        if url_re.match(link):
            maybe_title = Markup(' title="%s"') % title if title else ''
            return Markup('<a href="%s"%s>' + content + '</a>') % (link, maybe_title)
        else:
            return escape("[%s](%s)" % (content, link))

    def autolink(self, link, is_email):
        if url_re.match(link):
            return Markup('<a href="%s">%s</a>') % (link, link)
        else:
            return escape('<%s>' % link)


renderer = CustomRenderer(flags=['skip-html'])
md = m.Markdown(renderer, extensions=(
    'autolink', 'strikethrough', 'no-intra-emphasis', 'tables',
))


def render(markdown):
    return Markup(md(markdown))
