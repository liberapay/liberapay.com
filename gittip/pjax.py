import cStringIO
from tornado.template import _CodeWriter, _File


def outbound(response):
    """Muck with old Aspen internals to get PJAX barely working.
    """
    if not response.headers.get('Content-Type', '').startswith('text/html'):
        return
    if response.request.headers.get('X-PJAX') is None:
        return
    if 'pjax' not in response.request.context:
        return


    # Oh wow ...
    # ==========

    pjax = response.request.context['pjax']
    resource = response.request.resource
    renderer = resource.pages[2][0]
    loader, template = renderer.meta, renderer.compiled
    blocks = {}
    template.file.find_named_blocks(loader, blocks)
    snippet = blocks.get(pjax)
    if snippet is None:
        out = ""
    else:
        buffer = cStringIO.StringIO()
        writer = _CodeWriter(buffer, blocks, loader, template,
                             compress_whitespace=False)
        _File(snippet).generate(writer)
        python = buffer.getvalue()

        namespace = {}
        exec python in namespace
        out = namespace['_execute']()

    response.body = out
