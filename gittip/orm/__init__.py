from __future__ import unicode_literals
import os

from sqlalchemy import create_engine, MetaData
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session

class SQLAlchemy(object):
    def __init__(self):
        self.session = self.create_session()

    @property
    def engine(self):
        dburl = os.environ['DATABASE_URL']
        return create_engine(dburl)

    def create_session(self):
        session = scoped_session(sessionmaker())
        session.configure(bind=self.engine)
        return session

db = SQLAlchemy()

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

    def save(self):
        db.session.add(self)
        db.session.commit()

    def delete(self):
        db.session.delete(self)
        db.session.commit()

Base = declarative_base(cls=Model)
Base.metadata.bind = db.engine
Base.query = db.session.query_property()

metadata = MetaData()
metadata.bind = db.engine

all = [Base, db, metadata]


def rollback(*_):
    db.session.rollback()