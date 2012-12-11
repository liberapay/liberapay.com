from __future__ import unicode_literals
import os

from sqlalchemy import create_engine, event, MetaData
from sqlalchemy.exc import DisconnectionError
from sqlalchemy.ext.declarative import (
    declarative_base, _declarative_constructor)
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import Pool


class Model(object):
    def __init__(self, **kwargs):
        """
        Initializes a model by invoking the _declarative_constructor
        in SQLAlchemy. We do this for full control over construction
        of an object
        """
        _declarative_constructor(self, **kwargs)

    def __repr__(self):
        cols = self.__mapper__.c.keys()
        class_name = self.__class__.__name__
        items = ', '.join(['%s=%s' % (col, repr(getattr(self, col))) for col
                           in cols])
        return '%s(%s)' % (class_name, items)


dburl = os.environ['DATABASE_URL']
db_engine = create_engine(dburl)

Session = scoped_session(sessionmaker())
Session.configure(bind=db_engine)

Base = declarative_base(cls=Model, constructor=None)
Base.metadata.bind = db_engine
Base.query = Session.query_property()

metadata = MetaData()
metadata.bind = db_engine

all = [
    Base, Session, metadata
]


def rollback(*_):
    Session.rollback()
