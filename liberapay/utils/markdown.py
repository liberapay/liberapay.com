from markupsafe import Markup
import misaka as m  # http://misaka.61924.nl/

def render(markdown):
    return Markup(m.html(
        markdown,
        extensions=m.EXT_AUTOLINK | m.EXT_STRIKETHROUGH | m.EXT_NO_INTRA_EMPHASIS,
        render_flags=m.HTML_SKIP_HTML | m.HTML_TOC | m.HTML_SMARTYPANTS | m.HTML_SAFELINK
    ))
