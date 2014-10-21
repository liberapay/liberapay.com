import mock

from gratipay.models.participant import Participant
from gratipay.testing import Harness


class TestForVerifyEmail(Harness):

    @mock.patch.object(Participant, 'send_email')
    def change_email_address(self, address, username, send_email):
        url = "/%s/email.json" % username
        return self.client.POST(url, {'email': address}, auth_as=username)

    def verify_email(self, username, email, nonce, should_fail=False):
        url = '/%s/verify-email.html?email=%s&nonce=%s' % (username, email, nonce)
        G = self.client.GxT if should_fail else self.client.GET
        return G(url)

    def test_verify_email_without_adding_email(self):
        participant = self.make_participant('alice')
        response = self.verify_email(participant.username, '', 'sample-nonce', should_fail=True)
        assert response.code == 404

    def test_verify_email_wrong_nonce(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        self.verify_email(participant.username, 'alice@gmail.com', 'sample-nonce')
        expected = None
        actual = Participant.from_username(participant.username).email_address
        assert expected == actual

    def test_verify_email(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        nonce = Participant.from_username(participant.username)
        nonce = Participant.from_username('alice').get_email_nonce_and_ctime('alice@gmail.com')[0]
        self.verify_email(participant.username, 'alice@gmail.com', nonce)
        expected = 'alice@gmail.com'
        actual = Participant.from_username(participant.username).email_address
        assert expected == actual

    def test_confirmed_email_is_not_changed_after_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        nonce = Participant.from_username('alice').get_email_nonce_and_ctime('alice@gmail.com')[0]
        self.verify_email(participant.username, 'alice@gmail.com', nonce)
        self.change_email_address('alice@yahoo.com', participant.username)
        expected = 'alice@gmail.com'
        actual = Participant.from_username(participant.username).email_address
        assert expected == actual

    def test_unverified_email_is_set_changed_after_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        nonce = Participant.from_username('alice').get_email_nonce_and_ctime('alice@gmail.com')[0]
        self.verify_email(participant.username, 'alice@gmail.com', nonce)
        self.change_email_address('alice@yahoo.com', participant.username)
        expected = 'alice@yahoo.com'
        actual = Participant.from_username(participant.username).get_unverified_email()
        assert expected == actual

    def test_verify_email_after_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        nonce = Participant.from_username('alice').get_email_nonce_and_ctime('alice@gmail.com')[0]
        self.verify_email(participant.username, 'alice@gmail.com', nonce)
        self.change_email_address('alice@yahoo.com', participant.username)
        nonce = Participant.from_username('alice').get_email_nonce_and_ctime('alice@yahoo.com')[0]
        self.verify_email(participant.username, 'alice@yahoo.com', nonce)
        expected = 'alice@yahoo.com'
        actual = Participant.from_username(participant.username).email_address
        assert expected == actual

    def test_nonce_is_regenerated_on_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        nonce1 = Participant.from_username('alice').get_email_nonce_and_ctime('alice@gmail.com')[0]
        self.change_email_address('alice@gmail.com', participant.username)
        nonce2 = Participant.from_username('alice').get_email_nonce_and_ctime('alice@gmail.com')[0]
        assert nonce1 != nonce2
