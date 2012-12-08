from __future__ import unicode_literals
from decimal import Decimal

from aspen.testing import assert_raises
from gittip.participant import Participant
from gittip.testing import tip_graph
from psycopg2 import IntegrityError


def test_participant_can_be_instantiated():
    expected = Participant
    actual = Participant(None).__class__
    assert actual is expected, actual

def test_participant_can_absorb_another():
    with tip_graph(("foo", "bar", 1)) as context:
        Participant('foo').absorb('bar')

        expected = { 'absorptions': [1,0,0]
                   , 'tips': [1,0,0]
                    }
        actual = context.diff(compact=True)
        assert actual == expected, actual

def test_absorbing_yourself_sets_all_to_zero():
    with tip_graph(("foo", "bar", 1)) as context:
        Participant('foo').absorb('bar')

        expected = { 'amount': Decimal('0.00')
                   , 'tipper': 'foo'
                   , 'tippee': 'bar'
                    }
        actual = context.diff()['tips']['inserts'][0]
        del actual['ctime']; del actual['mtime']; del actual['id']
        assert actual == expected, actual

def test_alice_ends_up_tipping_bob_two_dollars():
    tips = [ ('alice', 'bob', 1)
           , ('alice', 'carl', 1)
            ]
    with tip_graph(*tips) as context:
        Participant('bob').absorb('carl')
        expected = Decimal('2.00')
        actual = context.diff()['tips']['inserts'][0]['amount']
        assert actual == expected, actual

def test_bob_ends_up_tipping_alice_two_dollars():
    tips = [ ('bob', 'alice', 1)
           , ('carl', 'alice', 1)
            ]
    with tip_graph(*tips) as context:
        Participant('bob').absorb('carl')
        expected = Decimal('2.00')
        actual = context.diff()['tips']['inserts'][0]['amount']
        assert actual == expected, actual

def test_ctime_comes_from_the_older_tip():
    tips = [ ('alice', 'bob', 1)
           , ('alice', 'carl', 1)
            ]
    with tip_graph(*tips) as context:
        Participant('bob').absorb('carl')

        tips = sorted(context.dump()['tips'].items())
        first, second = tips[0][1], tips[1][1]

        # sanity checks (these don't count :)
        assert len(tips) == 4
        assert first['ctime'] < second['ctime']
        assert first['tipper'], first['tippee'] == ('alice', 'bob')
        assert second['tipper'], second['tippee'] == ('alice', 'carl')

        expected = first['ctime']
        actual = context.diff()['tips']['inserts'][0]['ctime']
        assert actual == expected, actual

def test_absorbing_unknown_fails():
    tips = [ ('alice', 'bob', 1)
           , ('alice', 'carl', 1)
            ]
    with tip_graph(*tips) as context:
        assert_raises(IntegrityError, Participant('bob').absorb, 'jim')
        actual = context.diff()
        assert actual == {}, actual
