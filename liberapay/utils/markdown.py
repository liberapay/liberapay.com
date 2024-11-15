import re

from markupsafe import Markup
import misaka as m  # http://misaka.61924.nl/

from liberapay.website import website

# probably goto constants.py?
# https://developer.wordpress.org/reference/functions/wp_allowed_protocols/
ALLOWED_PROTOCOLS = [
    "http",
    "https",
    "ftp",
    "ftps",
    "mailto",
    "news",
    "irc",
    "irc6",
    "ircs",
    "gopher",
    "nntp",
    "feed",
    "telnet",
    "mms",
    "rtsp",
    "sms",
    "svn",
    "tel",
    "fax",
    "xmpp",
    "webcal",
    "urn",
]

_uri_re = re.compile(r"^(" + "|".join(ALLOWED_PROTOCOLS) + "):")
_internal_re = re.compile(r"^https://([\w\-]+\.)?liberapay\.(com|net|org)")


# check whether the link is an external link
def _is_internal_url(url: str) -> bool:
    return bool(_internal_re.match(url))

class CustomRenderer(m.SaferHtmlRenderer):
    # enable url-rewrite and block potential ones
    def __init__(self):
        self.canonical_host = website.env.canonical_host
        if not self.canonical_host.startswith(('http://', 'https://')):
            # make sure localhost is handled
            self.canonical_host = 'http://' + self.canonical_host

        super().__init__(link_rewrite=f"{self.canonical_host}/redirect?url={{url}}?back_to={self.canonical_host}")
        
    def autolink(self, raw_url, is_email):
        # override super's autolink function, add target="_blank"
        if self.check_url(raw_url):
            url = self.rewrite_url(('mailto:' if is_email else '') + raw_url)
            url = m.escape_html(url)
            return '<a href="%s" target="_blank">%s</a>' % (url, m.escape_html(raw_url))
        else:
            return m.escape_html('<%s>' % raw_url)
    
    def link(self, content, raw_url, title=''):
        # override super's link function, add target="_blank"
        if self.check_url(raw_url):
            url = self.rewrite_url(raw_url)
            maybe_title = ' title="%s"' % m.escape_html(title) if title else ''
            url = m.escape_html(url)
            return ('<a href="%s"%s target="_blank">' % (url, maybe_title))  + content + '</a>'
        else:
            return m.escape_html("[%s](%s)" % (content, raw_url))

    def check_url(self, url, is_image_src=False):
        return bool(_uri_re.match(url))
    
    def rewrite_url(self, url, is_image_src=False):
        rewrite = not _is_internal_url(url)
        if rewrite:
            return super().rewrite_url(m.escape_html(url, escape_slash=True), is_image_src)
        return url


renderer = CustomRenderer()
md = m.Markdown(
    renderer,
    extensions=(
        "autolink",
        "strikethrough",
        "no-intra-emphasis",
        "tables",
    ),
)


def render(markdown):
    return Markup(md(markdown))
