from hashlib import md5
from io import BytesIO

from aspen.simplates.pagination import parse_specline, split_and_escape
from babel.messages.extract import extract_python
import jinja2.ext


def extract_custom(extractor, *args, **kw):
    for match in extractor(*args, **kw):
        msg = match[2]
        if isinstance(msg, tuple) and msg[0] == '':
            unused = "<unused singular (hash=%s)>" % md5(msg[1].encode('utf8')).hexdigest()
            msg = (unused, msg[1], msg[2])
            match = (match[0], match[1], msg, match[3])
        yield match


def extract_jinja2_custom(*args, **kw):
    return extract_custom(jinja2.ext.babel_extract, *args, **kw)


def extract_python_custom(*args, **kw):
    return extract_custom(extract_python, *args, **kw)


def extract_spt(fileobj, *args, **kw):
    pages = list(split_and_escape(fileobj.read().decode('utf8')))
    npages = len(pages)
    for i, page in enumerate(pages, 1):
        f = BytesIO(b'\n' * page.offset + page.content.encode('utf8'))
        content_type, renderer = parse_specline(page.header)
        extractor = None
        python_page = i < 3 and i < npages and not page.header
        json_page = renderer == 'json_dump'
        if python_page or json_page:
            extractor = extract_python_custom
        else:
            extractor = extract_jinja2_custom
        if extractor:
            for match in extractor(f, *args, **kw):
                yield match
