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
        super().__init__(link_rewrite=f"{website.env.canonical_host}/redirect?url={{url}}")

    def check_url(self, url, is_image_src=False):
        return bool(_uri_re.match(url))
    
    def rewrite_url(self, url, is_image_src=False):
        rewrite = not _is_internal_url(url)
        if rewrite:
            return super().rewrite_url(url, is_image_src)
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
