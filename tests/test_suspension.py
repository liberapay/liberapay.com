from gittip.testing import load
from gittip.participant import Participant


def test_participants_start_out_unpayin_suspended():
    with load('participants', ('foo',)) as context:
        actual = context.dump()['participants']['foo']['payin_suspended']
        assert actual is False, actual

def test_suspend_suspends():
    with load('participants', ('foo',)) as context:
        Participant('foo').suspend_payin()
        actual = context.diff()['participants']['updates'][0]['payin_suspended']
        assert actual is True, actual

def test_suspend_changes_one_thing_only():
    with load('participants', ('foo',)) as context:
        Participant('foo').suspend_payin()
        actual = context.diff(compact=True)
        assert actual == {'participants': [0,1,0]}, actual

def test_suspend_is_a_noop_when_payin_suspended():
    with load('participants', {'id': 'foo', 'payin_suspended': True}) as context:
        Participant('foo').suspend_payin()
        actual = context.diff(compact=True)
        assert actual == {}, actual

def test_unsuspend_is_a_noop_when_not_payin_suspended():
    with load('participants', ('foo',)) as context:
        Participant('foo').unsuspend_payin()
        actual = context.diff(compact=True)
        assert actual == {}, actual

def test_unsuspend_unsuspends():
    with load('participants', {'id': 'foo', 'payin_suspended': True}) as context:
        Participant('foo').unsuspend_payin()
        actual = context.diff()['participants']['updates'][0]['payin_suspended']
        assert actual is False, actual

def test_unsuspend_changes_one_thing_only():
    with load('participants', {'id': 'foo', 'payin_suspended': True}) as context:
        Participant('foo').unsuspend_payin()
        actual = context.diff(compact=True)
        assert actual == {'participants': [0,1,0]}, actual
