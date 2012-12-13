from __future__ import unicode_literals
from decimal import Decimal

from aspen.testing import assert_raises
from gittip.participant import Participant, NeedConfirmation
from gittip.testing import tip_graph
from psycopg2 import IntegrityError


def test_need_confirmation1(): assert not NeedConfirmation(False, False, False)
def test_need_confirmation2(): assert     NeedConfirmation(False, False, True)
def test_need_confirmation3(): assert not NeedConfirmation(False, True, False)
def test_need_confirmation4(): assert     NeedConfirmation(False, True, True)
def test_need_confirmation5(): assert     NeedConfirmation(True, False, False)
def test_need_confirmation6(): assert     NeedConfirmation(True, False, True)
def test_need_confirmation7(): assert     NeedConfirmation(True, True, False)
def test_need_confirmation8(): assert     NeedConfirmation(True, True, True)


def test_participant_can_be_instantiated():
    expected = Participant
    actual = Participant(None).__class__
    assert actual is expected, actual


def scenario(scenario_function):
    def one(test_function):
        def two():
            scenario_function(test_function)
        two.__name__ = test_function.__name__
        return two
    return one

@scenario
def scenario_1(test_func):
    """Scenarios! :D

    We've got three live Gittip accounts: foo, bar, and baz.

    Each has a GitHub account connected.

    Foo has a tip pledged to deadbeef, which is a stub participant with a
    Twitter account connected.

    Bar claims deadbeef's Twitter account.

    What happens?!

    """
    tips = [ ("foo", "deadbeef", 1, True, False, False)
           , ("bar", None, "na", True, False, "na", "Twitter", "2345")
           , ("baz", "bar", 1)
            ]
    with tip_graph(*tips) as context:
        platform, user_id = context.resolve_elsewhere('deadbeef')[0]
        Participant('bar').take_over(platform, user_id)

        p = context.dump()['participants'].keys()
        context.deadbeef_archived_as = [x for x in p if len(x) > 3][0]

        test_func(context)


@scenario_1
def test_compact_diff_is_as_expected(context):
    expected = { 'absorptions': [1,0,0]
               , 'elsewhere': [0,1,0]
               , 'participants': [1,0,1]
               , 'tips': [3,1,0]
                }
    actual = context.diff(compact=True)
    assert actual == expected, actual

@scenario_1
def test_accounts_are_claimed_as_expected(context):
    expected = { "foo": True, "bar": True, "baz": True
               , context.deadbeef_archived_as: False
                }

    participants = context.dump()['participants'].items()
    actual = [(x[1]['id'], x[1]['claimed_time'] is not None) \
                                                         for x in participants]
    actual = dict(actual)

    assert actual == expected, actual

@scenario_1
def test_deadbeef_is_archived(context):
    expected = { 'absorbed_by': 'bar'
               , 'absorbed_was': 'deadbeef'
               , 'archived_as': context.deadbeef_archived_as
                }
    actual = context.dump()['absorptions'].values()[0]
    del actual['id'], actual['timestamp']
    assert actual == expected, actual

@scenario_1
def test_bar_has_two_dollars_in_tips(context):
    expected = Decimal('2.00')
    actual = Participant('bar').get_dollars_receiving()
    assert actual == expected, actual

@scenario_1
def test_foo_gives_to_bar_now(context):
    expected = Decimal('1.00')
    actual = Participant('foo').get_tip_to('bar')
    assert actual == expected, actual

@scenario_1
def test_foo_doesnt_gives_to_deadbeef_anymore(context):
    expected = Decimal('0.00')
    actual = Participant('foo').get_tip_to('deadbeef')
    assert actual == expected, actual

@scenario_1
def test_foo_doesnt_gives_to_whatever_deadbeef_was_archived_as_either(context):
    expected = Decimal('0.00')
    actual = Participant('foo').get_tip_to(context.deadbeef_archived_as)
    assert actual == expected, actual

@scenario_1
def test_attempts_to_change_archived_deadbeef_fail(context):
    participant = Participant(context.deadbeef_archived_as)
    assert_raises(IntegrityError, participant.change_id, 'zombeef')

@scenario_1
def test_there_is_no_more_deadbeef(context):
    actual = Participant('deadbeef').get_details()
    assert actual is None, actual


def test_cant_take_over_claimed_participant_without_confirmation():
    with tip_graph(("foo", "bar", 1)) as context:
        platform, user_id = context.resolve_elsewhere("bar")[0]
        func = Participant('foo').take_over
        assert_raises(NeedConfirmation, func, platform, user_id)

def test_taking_over_yourself_sets_all_to_zero():
    with tip_graph(("foo", "bar", 1)) as context:
        platform, user_id = context.resolve_elsewhere("bar")[0]
        Participant('foo').take_over(platform, user_id, have_confirmation=True)

        expected = { 'amount': Decimal('0.00')
                   , 'tipper': 'foo'
                   #, 'tippee': 'bar'  becomes a random id
                    }
        actual = context.diff()['tips']['inserts'][0]
        del actual['ctime'], actual['mtime'], actual['id'], actual['tippee']
        assert actual == expected, actual

def test_alice_ends_up_tipping_bob_two_dollars():
    tips = [ ('alice', 'bob', 1)
           , ('alice', 'carl', 1)
            ]
    with tip_graph(*tips) as context:
        platform, user_id = context.resolve_elsewhere('carl')[0]
        Participant('bob').take_over(platform, user_id, True)
        expected = Decimal('2.00')
        actual = context.diff()['tips']['inserts'][0]['amount']
        assert actual == expected, actual

def test_bob_ends_up_tipping_alice_two_dollars():
    tips = [ ('bob', 'alice', 1)
           , ('carl', 'alice', 1)
            ]
    with tip_graph(*tips) as context:
        platform, user_id = context.resolve_elsewhere('carl')[0]
        Participant('bob').take_over(platform, user_id, True)
        expected = Decimal('2.00')
        actual = context.diff()['tips']['inserts'][0]['amount']
        assert actual == expected, actual

def test_ctime_comes_from_the_older_tip():
    tips = [ ('alice', 'bob', 1)
           , ('alice', 'carl', 1)
            ]
    with tip_graph(*tips) as context:
        platform, user_id = context.resolve_elsewhere('carl')[0]
        Participant('bob').take_over(platform, user_id, True)

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

def test_connecting_unknown_account_fails():
    tips = [ ('alice', 'bob', 1)
           , ('alice', 'carl', 1)
            ]
    with tip_graph(*tips) as context:
        assert_raises( AssertionError
                     , Participant('bob').take_over
                     , 'GitHub'
                     , 'jim'
                      )
        actual = context.diff()
        assert actual == {}, actual
