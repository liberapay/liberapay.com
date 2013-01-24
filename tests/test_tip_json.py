import json
from nose.tools import assert_equal

from gittip.testing import TestClient
from gittip import db


CREATE_ACCOUNT = "INSERT INTO participants (id) VALUES (%s);"


def test_get_amount_and_total_back_from_api():
    "Test that we get correct amounts and totals back on POSTs to tip.json"
    client = TestClient()

    # First, create some test data
    # We need accounts
    db.execute(CREATE_ACCOUNT, ("test_tippee1",))
    db.execute(CREATE_ACCOUNT, ("test_tippee2",))
    db.execute(CREATE_ACCOUNT, ("test_tipper",))

    # We need to get ourselves a token!
    response = client.get('/')
    csrf_token = response.request.context['csrf_token']

    # Then, add a $1.50 and $3.00 tip
    response1 = client.post("/test_tippee1/tip.json",
                            {'amount': "1.00", 'csrf_token': csrf_token},
                            user='test_tipper')

    response2 = client.post("/test_tippee2/tip.json",
                            {'amount': "3.00", 'csrf_token': csrf_token},
                            user='test_tipper')

    # Confirm we get back the right amounts.
    first_data = json.loads(response1.body)
    second_data = json.loads(response2.body)
    assert_equal(first_data['amount'], "1.00")
    assert_equal(first_data['total_giving'], "1.00")
    assert_equal(second_data['amount'], "3.00")
    assert_equal(second_data['total_giving'], "4.00")
    assert_equal(False, True)
