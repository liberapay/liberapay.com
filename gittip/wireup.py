"""Wireup
"""
import os

import gittip
import psycopg2
import stripe
from gittip.postgres import PostgresManager
from psycopg2.extensions import cursor as RegularCursor 


def canonical():
    gittip.canonical_scheme = os.environ['CANONICAL_SCHEME']
    gittip.canonical_host = os.environ['CANONICAL_HOST']

def db():
    dburl = os.environ['DATABASE_URL']
    gittip.db = PostgresManager(dburl)

    # register hstore type (but don't use RealDictCursor)
    with gittip.db.get_connection() as conn:
        curs = conn.cursor(cursor_factory=RegularCursor)
        psycopg2.extras.register_hstore(curs, globally=True, unicode=True)

    return gittip.db

def billing():
    stripe.api_key= os.environ['STRIPE_SECRET_API_KEY']
    stripe.publishable_api_key= os.environ['STRIPE_PUBLISHABLE_API_KEY']
