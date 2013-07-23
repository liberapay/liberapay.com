from pyquery import PyQuery as pq


def outbound(response):
    """Do PJAX by pulling an element out of the rendered page.
    """
    if not response.headers.get('Content-Type', '').startswith('text/html'):
        return
    if response.request.headers.get('X-PJAX') is None:
        return
    if response.request.headers.get('X-PJAX-CONTAINER') is None:
        return

    selector = response.request.headers.get('X-PJAX-CONTAINER')
    response.body = pq(response.body)(selector).html().encode('utf-8')
