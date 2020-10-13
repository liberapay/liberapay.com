from types import SimpleNamespace


class LocalizedString(str):
    """A string with a `lang` attribute containing an ISO language code.
    """

    __slots__ = ('lang',)

    def __new__(cls, obj, lang):
        r = str.__new__(cls, obj)
        r.lang = lang
        return r


class Object(SimpleNamespace):
    """
    A namespace that supports both attribute-style and dict-style lookups and
    assignments. This is similar to a JavaScript object, hence the name.
    """

    def __init__(self, *d, **kw):
        self.__dict__.update(*d, **kw)

    def __contains__(self, key):
        return key in self.__dict__

    def __getitem__(self, key):
        return self.__dict__[key]

    def __setitem__(self, key, value):
        self.__dict__[key] = value

    def _asdict(self):
        # For compatibility with namedtuple classes
        return self.__dict__.copy()
