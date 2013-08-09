from __future__ import unicode_literals
import os

import gittip
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import OperationalError


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
        maxconn = int(os.environ['DATABASE_MAXCONN'])
        return create_engine(dburl, pool_size=maxconn, max_overflow=0)

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
        gittip.db.run("DELETE FROM memberships") # *sigh*
        gittip.db.run("DELETE FROM log_participant_number") # *sigh*
        tables = reversed(self.metadata.sorted_tables)
        for table in tables:
            try:
                self.session.execute(table.delete())
                self.session.commit()
            except OperationalError:
                self.session.rollback()
        self.session.remove()

    def drop_all(self):
        self.Model.metadata.drop_all(bind=self.engine)

    def create_all(self):
        self.Model.metadata.create_all(bind=self.engine)


db = SQLAlchemy()

all = [db]

def rollback(*_):
    db.session.rollback()
