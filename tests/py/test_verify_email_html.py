from gratipay.models.participant import Participant
from gratipay.testing import Harness


class TestForVerifyEmail(Harness):

    def change_email_address(self, address, username, should_fail=False):
        url = "/%s/email.json" % username
        if should_fail:
            response = self.client.PxST(url
                , {'email': address,}
                , auth_as=username
            )
        else:
            response = self.client.POST(url
                , {'email': address,}
                , auth_as=username
            )
        return response

    def verify_email(self, username, hash_string, should_fail=False):
        url = '/%s/verify-email.html?hash=%s' % (username , hash_string)
        if should_fail:
            response = self.client.GxT(url)
        else:
            response = self.client.GET(url)
        return response

    def test_verify_email_without_adding_email(self):
        participant = self.make_participant('alice')
        response = self.verify_email(participant.username,'sample-hash', should_fail=True)
        assert response.code == 404

    def test_verify_email_wrong_hash(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        self.verify_email(participant.username,'sample-hash')
        expected = False
        actual = Participant.from_username(participant.username).email.confirmed
        assert expected == actual

    def test_verify_email(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        hash_string = Participant.from_username(participant.username).email.hash
        self.verify_email(participant.username,hash_string)
        expected = True
        actual = Participant.from_username(participant.username).email.confirmed
        assert expected == actual

    def test_email_is_not_confirmed_after_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        hash_string = Participant.from_username(participant.username).email.hash
        self.verify_email(participant.username,hash_string)
        self.change_email_address('alice@yahoo.com', participant.username)
        expected = False
        actual = Participant.from_username(participant.username).email.confirmed
        assert expected == actual

    def test_verify_email_after_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        hash_string = Participant.from_username(participant.username).email.hash
        self.verify_email(participant.username,hash_string)
        self.change_email_address('alice@yahoo.com', participant.username)
        hash_string = Participant.from_username(participant.username).email.hash
        self.verify_email(participant.username,hash_string)
        expected = True
        actual = Participant.from_username(participant.username).email.confirmed
        assert expected == actual

    def test_hash_is_regenerated_on_update(self):
        participant = self.make_participant('alice', claimed_time="now")
        self.change_email_address('alice@gmail.com', participant.username)
        hash_string_1 = Participant.from_username(participant.username).email.hash
        self.change_email_address('alice@gmail.com', participant.username)
        hash_string_2 = Participant.from_username(participant.username).email.hash
        assert hash_string_1 != hash_string_2