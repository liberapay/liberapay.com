from postgres.orm import Model
from psycopg2.extensions import adapt, AsIs

from ..website import website


class Encrypted(Model):

    typname = "encrypted"

    def __init__(self, data):
        data['payload'] = bytes(data['payload'])
        Model.__init__(self, data)

    def __conform__(self, protocol):
        return AsIs(
            "('fernet',%s,%s)::encrypted" % (adapt(self.payload), adapt(self.ts))
        )

    def decrypt(self):
        return website.cryptograph.decrypt(self.scheme, self.payload)
