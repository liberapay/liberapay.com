from binascii import b2a_base64
from datetime import datetime, timedelta
from math import log
import os
from os import urandom
import warnings

import boto3
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from pando.utils import utc, utcnow
from psycopg2.extras import execute_batch

from ..models.encrypted import Encrypted
from ..utils import cbor
from ..website import website


def get_random_string(length=32, altchars=None) -> str:
    """
    Returns a securely generated random string.

    Args:
        length (int): the number of base64 characters to return
        altchars (bytes): optional replacement characters for `+` and `/`, e.g. b'-_'

    The default length (32) returns a value with 192 bits of entropy (log(64**32, 2)).
    """
    token = b2a_base64(urandom(length * 6 // 8 + 1))[:length]
    if altchars:
        token = token.replace(b'+', altchars[0]).replace(b'/', altchars[1])
    return token.decode('ascii')


def constant_time_compare(val1, val2) -> bool:
    """
    Returns True if the two strings are equal, False otherwise.

    The time taken is independent of the number of characters that match.
    """
    if len(val1) != len(val2):
        return False
    result = 0
    if isinstance(val1, bytes) and bytes != str:
        for x, y in zip(val1, val2):
            result |= x ^ y
    else:
        for x, y in zip(val1, val2):
            result |= ord(x) ^ ord(y)
    return result == 0


class CryptoWarning(Warning):
    "For when a cryptographic function is being used in a potentially unsafe way."


class Cryptograph:
    """Symmetric encryption and decryption for the storage of sensitive data.

    We currently rely on Fernet, which was the algorithm adopted by Gratipay:
    https://github.com/gratipay/gratipay.com/pull/3998#issuecomment-216227070

    For encryption Fernet uses the AES cipher in CBC mode with PKCS7 padding and
    a 128 bits key. For authentication it uses HMAC-SHA256 with another 128 bits
    key.

    Fernet messages contain the timestamp at which they were generated *in plain
    text*. This isn't a problem for us since we want to store the time at which
    the data was encrypted in order to facilitate key rotation.

    We use CBOR (Concise Binary Object Representation) to serialize objects
    before encryption. Compared to JSON, CBOR is faster to parse and serialize,
    more compact, and extensible (it can represent any data type using "tags").
    More info on CBOR: http://cbor.io/ https://tools.ietf.org/html/rfc7049
    """

    KEY_ROTATION_DELAY = timedelta(weeks=1)

    def __init__(self):
        if website.env.aws_secret_access_key:
            sm = self.secrets_manager = boto3.client('secretsmanager', region_name='eu-west-1')
            secret = sm.get_secret_value(SecretId='Fernet')
            rotation_start = secret['CreatedDate'].replace(tzinfo=utc)
            keys = secret['SecretString'].split()
        else:
            self.secrets_manager = None
            parts = os.environ['SECRET_FERNET_KEYS'].split()
            rotation_start = datetime(*map(int, parts[0].split('-')), 0, 0, 0, 0, utc)
            keys = parts[1:]
        self.fernet_rotation_start = rotation_start
        self.fernet_keys = [k.encode('ascii') for k in keys]
        self.fernet = MultiFernet([Fernet(k) for k in self.fernet_keys])

    def encrypt_dict(self, dic, allow_single_key=False):
        """Serialize and encrypt a dictionary for storage in the database.

        Encrypting partially predictable data may help an attacker break the
        encryption key, so to make our data less predictable we randomize the
        order of the dict's items before serializing it.

        For this to be effective the CBOR serializer must not sort the items
        again in an attempt to produce Canonical CBOR, so we explicitly pass
        `canonical=False` to the `cbor.dumps` function.

        In addition, the dict must not contain only one key if that key is
        predictable, so a `CryptoWarning` is emitted when `dic` only contains
        one key, unless `allow_single_key` is set to `True`.
        """
        dic = self.randomize_dict(dic, allow_single_key=allow_single_key)
        serialized = cbor.dumps(dic, canonical=False)
        encrypted = self.fernet.encrypt(serialized)
        return Encrypted(('fernet', encrypted, utcnow()))

    def decrypt(self, scheme, payload):
        """Decrypt and reconstruct an object stored in the database.
        """
        if scheme == 'fernet':
            decrypted = self.fernet.decrypt(payload)
        else:
            raise ValueError('unknown encryption scheme %r' % scheme)
        return cbor.loads(decrypted)

    @staticmethod
    def randomize_dict(dic, allow_single_key=False):
        """Randomize the order of a dictionary's items.

        Emits a `CryptoWarning` if `dic` only contains one key, unless
        `allow_single_key` is set to `True`.
        """
        if not isinstance(dic, dict):
            raise TypeError("expected a dict, got %s" % type(dic))
        # Compute the number of random bytes needed based on the size of the dict
        n = len(dic)
        if n < 2:
            # Can't randomize the order if the dict contains less than 2 items
            if n == 1 and not allow_single_key:
                warnings.warn("dict only contains one key", CryptoWarning)
            return dic
        n = int(log(n, 2) // 8) + 2
        # Return a new dict sorted randomly
        return dict(sorted(dic.items(), key=lambda t: urandom(n)))

    def rotate_key(self):
        """Generate a new key and send it to the secrets manager.
        """
        keys = b' '.join([Fernet.generate_key()] + self.fernet_keys).decode()
        if self.secrets_manager:
            self.secrets_manager.update_secret(SecretId='Fernet', SecretString=keys)
        else:
            keys = utcnow().date().isoformat() + ' ' + keys
            print("No secrets manager, updating the key storage is up to you.")
        return keys

    def rotate_message(self, msg, force=False):
        """Re-encrypt a single message using the current primary key.

        The original timestamp included in the message is always preserved.
        Moreover the entire message is returned unchanged if it was already
        encrypted from the latest key and `force` is `False` (the default).

        `InvalidToken` is raised if decryption fails.
        """
        timestamp, data = Fernet._get_unverified_token_data(msg)
        for i, fernet in enumerate(self.fernet._fernets):
            try:
                p = fernet._decrypt_data(data, timestamp, None)
            except InvalidToken:
                continue
            if i == 0 and not force:
                # This message was encrypted using the latest key, return it
                return msg
            break
        else:
            raise InvalidToken

        iv = os.urandom(16)
        return self.fernet._fernets[0]._encrypt_from_parts(p, timestamp, iv)

    def rotate_stored_data(self, wait=True):
        """Re-encrypt all the sensitive information stored in our database.

        This function is a special kind of "cron job" that returns either the
        number of seconds to wait before it should be called again, or `None`
        indicating that all the ciphertexts are up-to-date.

        Rows are processed in batches of 50. Timestamps are used to keep track of
        progress and to avoid overwriting new data with re-encrypted old data.

        The update only starts one week after the new key was generated, unless
        `wait` is set to `False`. This delay is to "ensure" that the previous
        key is no longer being used to encrypt new data.
        """
        if wait:
            update_start = self.fernet_rotation_start + self.KEY_ROTATION_DELAY
            now = utcnow()
            if now < update_start:
                return (update_start - now).total_seconds()
        else:
            update_start = utcnow()

        while True:
            with website.db.get_cursor() as cursor:
                batch = cursor.all("""
                    SELECT id, info
                      FROM identities
                     WHERE (info).ts <= %s
                  ORDER BY (info).ts ASC
                     LIMIT 50
                """, (update_start,))
                if not batch:
                    return

                sql = """
                    UPDATE identities
                       SET info = ('fernet', %s, current_timestamp)::encrypted
                     WHERE id = %s
                       AND (info).ts = %s;
                """
                args_list = [
                    (self.rotate_message(r.info.payload), r.id, r.info.ts)
                    for r in batch
                ]
                execute_batch(cursor, sql, args_list)
