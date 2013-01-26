from __future__ import unicode_literals
import os

from sqlalchemy import create_engine
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

    @property
    def metadata(self):
        return self.Model.metadata

    def create_session(self):
        session = scoped_session(sessionmaker())
        session.configure(bind=self.engine)
        return session

    def make_declarative_base(self):
        base = declarative_base(cls=Model)
        base.query = self.session.query_property()
        return base

    def empty_tables(self):
        for table in reversed(self.metadata.sorted_tables):
            self.session.execute(table.delete())
        self.session.commit()
        self.session.remove()

    def drop_all(self):
        self.Model.metadata.drop_all(bind=self.engine)

    def create_all(self):
        self.Model.metadata.create_all(bind=self.engine)


db = SQLAlchemy()

all = [db]

def rollback(*_):
    db.session.rollback()
