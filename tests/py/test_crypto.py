import os
import warnings

import pytest

from liberapay.security.crypto import CryptoWarning
from liberapay.testing import Harness


class TestCrypto(Harness):

    def test_database_round_trip(self):
        data = {'foo': 'bar', 0: 1}
        r = self.db.one("SELECT %s", (self.website.cryptograph.encrypt_dict(data),))
        assert data == r.decrypt()

    def test_key_rotation(self):
        cryptograph = self.website.cryptograph
        # Insert some encrypted data
        jane = self.make_participant('jane')
        info = {
            "name": "Jane Doe",
            "nationality": None,
            "birthdate": "2019-01-19",
            "postal_address": {
                "country": "FR",
            },
        }
        ts = self.db.one("""
            INSERT INTO identities
                        (participant, info)
                 VALUES (%s, %s)
              RETURNING (info).ts
        """, (jane.id, cryptograph.encrypt_dict(info)))

        # Rotate the key
        keys = cryptograph.rotate_key()
        today, new_key, old_key = keys.split()
        assert new_key != old_key
        os.environ['SECRET_FERNET_KEYS'] = keys
        cryptograph.__init__()

        # Attempt to rotate the data, but it's too soon
        r = cryptograph.rotate_stored_data(wait=True)
        assert r > 0
        new_ts = self.db.one("SELECT (info).ts FROM identities")
        assert new_ts == ts

        # Rotate the data without waiting
        cryptograph.rotate_stored_data(wait=False)
        new_info = self.db.one("SELECT info FROM identities")
        assert new_info.ts > ts
        assert new_info.decrypt() == info

        # Rotate the data again, this time it shouldn't change
        cryptograph.rotate_stored_data(wait=False)
        new_info_2 = self.db.one("SELECT info FROM identities")
        assert new_info_2.payload == new_info.payload

    def test_encrypt_dict_warns_of_single_key(self):
        with pytest.warns(CryptoWarning, match="dict only contains one key") as w:
            self.website.cryptograph.encrypt_dict({"long_single_key": None})
        assert len(w) == 1
        with warnings.catch_warnings(record=True) as w:
            self.website.cryptograph.encrypt_dict({})
            self.website.cryptograph.encrypt_dict({0: 1, 2: 3, 4: 5})
        assert len(w) == 0

    def test_encrypt_dict_randomizes_order(self):
        cryptograph = self.website.cryptograph
        data = {
            "name": "Jane Doe",
            "nationality": None,
            "birthdate": "2019-01-20",
            "postal_address": {
                "country": "FR",
            },
        }
        decrypted = set([
            cryptograph.fernet.decrypt(cryptograph.encrypt_dict(data).payload)
            for i in range(200)
        ])
        # A dict containing 4 items can be serialized in 24 different orders.
        assert len(decrypted) >= 20
        assert len(decrypted) <= 24
