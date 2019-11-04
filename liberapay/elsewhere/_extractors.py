"""Helper functions to extract data from API responses
"""

from functools import reduce
import json
import logging
from operator import getitem
import xml.etree.ElementTree as ET


logger = logging.getLogger('liberapay.elsewhere')


def _getitemchain(o, *keys):
    return reduce(getitem, keys, o)


def _popitemchain(obj, *keys):
    objs = [obj]
    for key in keys[:-1]:
        objs.append(objs[-1][key])
    r = objs[-1].pop(keys[-1])
    for o, k in reversed(list(zip(objs[:-1], keys[:-1]))):
        if len(o[k]) != 0:
            break
        o.pop(k)
    return r


def any_key(*keys, **kw):
    clean = kw.pop('clean', lambda a: a)
    def f(self, extracted, info, *default):
        for key in keys:
            chain = (key,) if not isinstance(key, (list, tuple)) else key
            try:
                v = _getitemchain(info, *chain)
            except (KeyError, TypeError):
                continue
            if v:
                v = clean(v)
            if not v:
                continue
            _popitemchain(info, *chain)
            return v
        if default:
            return default[0]
        msg = 'Unable to find any of the keys %s in %s API response:\n%s'
        msg %= keys, self.name, json.dumps(info, indent=4)
        logger.error(msg)
        raise KeyError(msg)
    return f


def key(k, clean=lambda a: a):
    def f(self, extracted, info, *default):
        try:
            v = info.pop(k, *default)
        except KeyError:
            msg = 'Unable to find key "%s" in %s API response:\n%s'
            logger.error(msg % (k, self.name, json.dumps(info, indent=4)))
            raise
        if v:
            v = clean(v)
        if not v and not default:
            msg = 'Key "%s" has an empty value in %s API response:\n%s'
            msg %= (k, self.name, json.dumps(info, indent=4))
            logger.error(msg)
            raise ValueError(msg)
        return v
    return f


def drop_keys(*keys):
    def f(self, info):
        for k in keys:
            if callable(k):
                for k2 in list(info.keys()):
                    if k(k2):
                        info.pop(k2)
            else:
                info.pop(k, None)
    return f


class _NotAvailable:

    def __bool__(self):
        return False

    def __call__(self, extracted, info, default):
        return default


not_available = _NotAvailable()


def xpath(path, attr=None, clean=lambda a: a):
    def f(self, extracted, info, *default):
        try:
            l = info.findall(path)
            if len(l) > 1:
                msg = 'The xpath "%s" matches more than one element in %s API response:\n%s'
                msg %= (path, self.name, ET.tostring(info))
                logger.error(msg)
                raise ValueError(msg)
            v = l[0].get(attr) if attr else ET.tostring(l[0], encoding='utf8', method='text')
        except IndexError:
            if default:
                return default[0]
            msg = 'Unable to find xpath "%s" in %s API response:\n%s'
            msg %= (path, self.name, ET.tostring(info))
            logger.error(msg)
            raise IndexError(msg)
        except KeyError:
            if default:
                return default[0]
            msg = 'The element has no "%s" attribute in %s API response:\n%s'
            msg %= (attr, self.name, ET.tostring(info))
            logger.error(msg)
            raise KeyError(msg)
        if v:
            v = clean(v)
        if not v and not default:
            msg = 'The xpath "%s" points to an empty value in %s API response:\n%s'
            msg %= (path, self.name, ET.tostring(info))
            logger.error(msg)
            raise ValueError(msg)
        return v
    return f
