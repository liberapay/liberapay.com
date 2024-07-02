import json

from liberapay.testing import Harness


class TestTipsJson(Harness):

    def test_post(self):

        self.make_participant("test_tippee1")
        self.make_participant("test_tippee2")
        test_tipper = self.make_participant("test_tipper")

        data = [
            {'username': 'test_tippee1', 'amount': '1.00', 'period': 'weekly'},
            {'username': 'test_tippee2', 'amount': '2.00', 'period': 'weekly'}
        ]

        response = self.client.POST('/test_tipper/tips.json',
                                    body=json.dumps(data).encode('ascii'),
                                    content_type='application/json',
                                    auth_as=test_tipper,
                                    )

        assert response.code == 200
        assert len(json.loads(response.text)) == 2

        data = [{'username': 'test_tippee2', 'amount': '1.00', 'period': 'weekly'}]
        response = self.client.POST('/test_tipper/tips.json',
                                    body=json.dumps(data).encode('ascii'),
                                    content_type='application/json',
                                    auth_as=test_tipper,
                                    )

        assert response.code == 200

        response = self.client.GET('/test_tipper/tips.json', auth_as=test_tipper)
        assert response.code == 200
        assert len(json.loads(response.text)) == 2

    def test_get_response(self):
        test_tipper = self.make_participant("test_tipper")

        response = self.client.GET('/test_tipper/tips.json', auth_as=test_tipper)

        assert response.code == 200
        assert len(json.loads(response.text)) == 0  # empty array

    def test_get_response_with_tips(self):
        self.make_participant("test_tippee1")
        test_tipper = self.make_participant("test_tipper")

        response = self.client.POST('/test_tippee1/tip.json',
                                    {'amount': '1.00', 'period': 'weekly'},
                                    auth_as=test_tipper,
                                    json=True,
                                    )
        data = json.loads(response.text)
        assert response.code == 200
        assert data['amount'] == {"amount": "1.00", "currency": "EUR"}

        response = self.client.GET('/test_tipper/tips.json', auth_as=test_tipper)
        data = json.loads(response.text)[0]

        assert response.code == 200
        assert data['tippee']['username'] == 'test_tippee1'
        assert data['amount'] == {"amount": "1.00", "currency": "EUR"}

    def test_malformed_body(self):
        alice = self.make_participant('alice')
        r = self.client.PxST(
            '/alice/tips.json', body=b'a', content_type=b'application/json',
            auth_as=alice,
        )
        assert r.code == 400
