from __future__ import division, print_function, unicode_literals

from markupsafe import Markup, escape, text_type


def jsonml(l):
    node = '<' + l[0]
    i = 1
    if isinstance(l[1], dict):
        i = 2
        for k, v in l[1].items():
            node += ' ' + k + '="' + text_type(escape(v)) + '"'
    node += '>'
    for c in l[i:]:
        if isinstance(c, list):
            node += text_type(jsonml(c))
        else:
            node += text_type(escape(c))
    node += '</' + l[0] + '>'
    return Markup(node)
