import misaka  # http://misaka.61924.nl/

m = misaka

def render(markdown):
    return misaka.html( markdown
                      , extensions=m.EXT_AUTOLINK | m.EXT_STRIKETHROUGH
                      , render_flags=m.HTML_SKIP_HTML | m.HTML_TOC | m.HTML_SMARTYPANTS
                       )
