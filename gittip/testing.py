"""Helpers for testing Gittip.
"""
from os.path import join, dirname, realpath

from gittip import wireup


SCHEMA = open(join(realpath(dirname(__file__)), "..", "schema.sql")).read()

def create_schema(db):
    db.execute(SCHEMA)

def populate_db_with_dummy_data(db):
    from gittip.networks import github
    github.upsert({"id": u"1775515", "login": u"lgtest"})
    github.upsert({"id": u"1903357", "login": u"lglocktest"})
    github.upsert({"id": u"1933953", "login": u"gittip-test-0"})
    github.upsert({"id": u"1933959", "login": u"gittip-test-1"})
    github.upsert({"id": u"1933965", "login": u"gittip-test-2"})
    github.upsert({"id": u"1933967", "login": u"gittip-test-3"})


if __name__ == "__main__":
    db = wireup.db() 
    populate_db_with_dummy_data(db)
