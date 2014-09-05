import misaka

def render(markdown):
    m = misaka  # http://misaka.61924.nl/
    return misaka.html( markdown
                      , extensions=m.EXT_AUTOLINK | m.EXT_STRIKETHROUGH
                      , render_flags=m.HTML_SKIP_HTML | m.HTML_TOC | m.HTML_SMARTYPANTS
                       )
