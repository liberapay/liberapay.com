from __future__ import unicode_literals
import os
import pdb

from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

class Model(object):
    def __repr__(self):
        cols = self.__mapper__.c.keys()
        class_name = self.__class__.__name__
        items = ', '.join(['%s=%s' % (col, repr(getattr(self, col))) for col
                           in cols])
        return '%s(%s)' % (class_name, items)

    def attrs_dict(self):
        keys = self.__mapper__.c.keys()
        attrs = {}
        for key in keys:
            attrs[key] = getattr(self, key)
        return attrs

class SQLAlchemy(object):
    def __init__(self):
        self.session = self.create_session()
        self.Model = self.make_declarative_base()

    @property
    def engine(self):
        dburl = os.environ['DATABASE_URL']
        return create_engine(dburl)

    def create_session(self):
        session = scoped_session(sessionmaker())
        session.configure(bind=self.engine)
        return session

    def make_declarative_base(self):
        base = declarative_base(cls=Model)
        base.query = self.session.query_property()
        return base

db = SQLAlchemy()

all = [db]

def rollback(*_):
    db.session.rollback()