from gittip.testing import load, serve_request


def participants(foo_starts_suspicious=None):
    participants = ( {"id": "foo"}
                   , {"id": "bar", "is_admin": True}
                    )
    if foo_starts_suspicious is not None:
        participants[0]["is_suspicious"] = foo_starts_suspicious
    return load('participants', *participants)


def toggle_is_suspicious():
    response = serve_request('/foo/toggle-is-suspicious.json', user='bar')
    return response.body


def test_participants_start_out_with_is_suspicious_None():
    with participants() as context:
        actual = context.dump()['participants']['foo']['is_suspicious']
        assert actual is None, actual

def test_toggling_NULL_gives_true():
    with participants() as context:
        toggle_is_suspicious()
        actual = context.diff()['participants']['updates'][1]['is_suspicious']
        assert actual is True, actual

def test_toggling_changes_two_things():
    with participants() as context:
        toggle_is_suspicious()
        actual = context.diff(compact=True)
        assert actual == {'participants': [0,2,0]}, actual

def test_but_the_first_thing_is_just_bars_session():
    with participants() as context:
        toggle_is_suspicious()
        expected = ('bar', ['id', 'session_expires', 'session_token'])
        second = context.diff()['participants']['updates'][0]
        actual = (second['id'], sorted(second.keys()))
        assert actual == expected, actual

def test_toggling_true_gives_false():
    with participants(True) as context:
        toggle_is_suspicious()
        actual = context.diff()['participants']['updates'][1]['is_suspicious']
        assert actual is False, actual

def test_toggling_false_gives_true():
    with participants(False) as context:
        toggle_is_suspicious()
        actual = context.diff()['participants']['updates'][1]['is_suspicious']
        assert actual is True, actual
