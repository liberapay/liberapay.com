from __future__ import absolute_import, division, print_function, unicode_literals

import re

from markupsafe import Markup, escape
import misaka as m  # http://misaka.61924.nl/


url_re = re.compile(r'^(https?|xmpp):')


class CustomRenderer(m.HtmlRenderer):

    def link(self, content, link, title=''):
        if url_re.match(link):
            maybe_title = Markup(' title="%s"') % title if title else ''
            return Markup('<a href="%s"%s>%s</a>') % (link, maybe_title, content)
        else:
            return escape("[%s](%s)" % (content, link))

    def autolink(self, link, is_email):
        if url_re.match(link):
            return Markup('<a href="%s">%s</a>') % (link, link)
        else:
            return escape('<%s>' % link)


renderer = CustomRenderer(flags=m.HTML_SKIP_HTML)
md = m.Markdown(renderer, extensions=('autolink', 'strikethrough', 'no-intra-emphasis'))


def render(markdown):
    return Markup(md(markdown))
