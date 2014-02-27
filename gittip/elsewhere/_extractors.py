"""Helper functions to extract data from API responses
"""
from __future__ import unicode_literals

import json
import xml.etree.ElementTree as ET

from aspen import log


def key(k, clean=lambda a: a):
    def f(self, info, *default):
        try:
            v = info.pop(k, *default)
        except KeyError:
            msg = 'Unable to find key "%s" in %s API response:\n%s'
            log(msg % (k, self.name, json.dumps(info, indent=4)))
            raise
        if v:
            v = clean(v)
        if not v and not default:
            msg = 'Key "%s" has an empty value in %s API response:\n%s'
            msg %= (k, self.name, json.dumps(info, indent=4))
            log(msg)
            raise ValueError(msg)
        return v
    return f


def not_available(self, info, default):
    return default


def xpath(path, attr=None, clean=lambda a: a):
    def f(self, info, *default):
        try:
            l = info.findall(path)
            if len(l) > 1:
                msg = 'The xpath "%s" matches more than one element in %s API response:\n%s'
                msg %= (path, self.name, ET.tostring(info))
                log(msg)
                raise ValueError(msg)
            v = l[0].get(attr) if attr else l[0]
        except IndexError:
            if default:
                return default[0]
            msg = 'Unable to find xpath "%s" in %s API response:\n%s'
            msg %= (path, self.name, ET.tostring(info))
            log(msg)
            raise IndexError(msg)
        except KeyError:
            if default:
                return default[0]
            msg = 'The element has no "%s" attribute in %s API response:\n%s'
            msg %= (attr, self.name, ET.tostring(info))
            log(msg)
            raise KeyError(msg)
        if v:
            v = clean(v)
        if not v and not default:
            msg = 'The xpath "%s" points to an empty value in %s API response:\n%s'
            msg %= (path, self.name, ET.tostring(info))
            log(msg)
            raise ValueError(msg)
        return v
    return f
