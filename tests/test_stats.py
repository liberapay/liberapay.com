from datetime import datetime
from decimal import Decimal

from gittip import wireup
from gittip.testing import load, load_simplate, serve_request, tip_graph
from gittip.billing.payday import Payday
from gittip.participant import Participant
from mock import patch


# commaize

simplate = load_simplate('/about/stats.html')
commaize = simplate.pages[0]['commaize']

def test_commaize_commaizes():
    actual = commaize(1000.0)
    assert actual == "1,000", actual

def test_commaize_commaizes_and_obeys_decimal_places():
    actual = commaize(1000, 4)
    assert actual == "1,000.0000", actual


# chart of giving

def check_tip_distribution(participant_id):
    return Participant(participant_id).get_tip_distribution()


def test_get_chart_of_receiving_handles_a_tip():
    tip = ("foo", "bar", "3.00", True)
    expected = ( [[Decimal('3.00'), 1, Decimal('3.00'), 1.0, Decimal('1')]]
               , 1.0, Decimal('3.00')
                )
    with tip_graph(tip):
        actual = check_tip_distribution(u'bar')
        assert actual == expected, actual

def test_get_chart_of_receiving_handles_a_non_standard_amount():
    tip = ("foo", "bar", "5.37", True)
    expected = ( [[-1, 1, Decimal('5.37'), 1.0, Decimal('1')]]
               , 1.0, Decimal('5.37')
                )
    with tip_graph(tip):
        actual = check_tip_distribution(u'bar')
        assert actual == expected, actual

def test_get_chart_of_receiving_handles_no_tips():
    expected = ([], 0.0, Decimal('0.00'))
    with tip_graph():
        actual = check_tip_distribution(u'foo')
        assert actual == expected, actual

def test_get_chart_of_receiving_handles_multiple_tips():
    tips = [ ("foo", "bar", "1.00", True)
           , ("baz", "bar", "3.00", True)
            ]
    expected = ( [ [Decimal('1.00'), 1L, Decimal('1.00'), 0.5, Decimal('0.25')]
                 , [Decimal('3.00'), 1L, Decimal('3.00'), 0.5, Decimal('0.75')]
                  ]
               , 2.0, Decimal('4.00')
                )
    with tip_graph(*tips):
        actual = check_tip_distribution(u'bar')
        assert actual == expected, actual

def test_get_chart_of_receiving_ignores_bad_cc():
    tips = [ ("foo", "bar", "1.00", True)
           , ("baz", "bar", "3.00", False)
            ]
    expected = ( [[Decimal('1.00'), 1L, Decimal('1.00'), 1, Decimal('1')]]
               , 1.0, Decimal('1.00')
                )
    with tip_graph(*tips):
        actual = check_tip_distribution(u'bar')
        assert actual == expected, actual

def test_get_chart_of_receiving_ignores_missing_cc():
    tips = [ ("foo", "bar", "1.00", True)
           , ("baz", "bar", "3.00", None)
            ]
    expected = ( [[Decimal('1.00'), 1L, Decimal('1.00'), 1, Decimal('1')]]
               , 1.0, Decimal('1.00')
                )
    with tip_graph(*tips):
        actual = check_tip_distribution(u'bar')
        assert actual == expected, actual


# rendering

def get_stats_page():
    #response = handle('/about/stats.html')
    response = serve_request('/about/stats.html')
    return response.body


@patch('datetime.datetime')
def test_stats_description_accurate_during_payday_run(mock_datetime):
    """Test that stats page takes running payday into account.

    This test was originally written to expose the fix required for
    https://github.com/zetaweb/www.gittip.com/issues/92.
    """
    with load() as context:
        a_thursday = datetime(2012, 8, 9, 12, 00, 01)
        mock_datetime.utcnow.return_value = a_thursday

        wireup.billing()
        pd = Payday(context.db)
        pd.start()

        body = get_stats_page()
        assert "is changing hands <b>right now!</b>" in body, body
        pd.end()

@patch('datetime.datetime')
def test_stats_description_accurate_outside_of_payday(mock_datetime):
    """Test stats page outside of the payday running"""
    with load() as context:
        a_monday = datetime(2012, 8, 6, 12, 00, 01)
        mock_datetime.utcnow.return_value = a_monday

        pd = Payday(context.db)
        pd.start()

        body = get_stats_page()
        assert "is ready for <b>this Thursday</b>" in body, body
        pd.end()
