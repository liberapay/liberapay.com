"""This module encapsulates billing logic and db access.
"""
from __future__ import unicode_literals

import balanced


class BalancedThing(object):
    """Represent either a credit card or a bank account.
    """

    thing_type = None           # either 'card' or 'bank_account'
    keys_to_attr_paths = None   # set to a mapping in subclasses

    _customer = None    # underlying balanced.Customer object
    _thing = None       # underlying balanced.{BankAccount,Card} object

    def __getitem__(self, key):
        """Given a name, return a unicode.

        Allow subclasses to provide a flat set of keys, which, under the hood,
        might be nested attributes and/or keys. The traversal path is relative
        to _thing (not self!).

        """
        attr_path = self.keys_to_attr_paths.get(key, key)

        out = None
        if self._customer is not None and self._thing is not None:
            out = self._thing
            for val in attr_path.split('.'):
                if type(out) is dict:
                    # this lets us reach into the meta dict
                    out = out.get(val)
                else:
                    try:
                        out = getattr(out, val)
                    except AttributeError:
                        raise KeyError("{} not found".format(val))
                if out is None:
                    break

        if out is None:
            # Default to ''; see https://github.com/gratipay/gratipay.com/issues/2161.
            out = ''

        return out

    def __init__(self, balanced_customer_href):
        """Given a Balanced account_uri, load data from Balanced.
        """
        if balanced_customer_href is None:
            return

        # XXX Indexing is borken. See:
        # https://github.com/balanced/balanced-python/issues/10

        self._customer = balanced.Customer.fetch(balanced_customer_href)

        things = getattr(self._customer, self.thing_type+'s')\
            .filter(is_valid=True).all()
        nvalid = len(things)

        if nvalid == 0:
            self._thing = None
        elif nvalid == 1:
            self._thing = things[0]
        else:
            msg = "%s has %d valid %ss"
            msg %= (balanced_customer_href, len(things), self.thing_type)
            raise RuntimeError(msg)

    @property
    def is_setup(self):
        return self._thing is not None


class BalancedCard(BalancedThing):
    """This is a dict-like wrapper around a Balanced credit card.
    """

    thing_type = 'card'

    keys_to_attr_paths = {
        'id': 'customer.href',
        'address_1': 'address.line1',
        'address_2': 'meta.address_2',
        'country': 'meta.country',
        'city_town': 'meta.city_town',
        'zip': 'address.postal_code',
        # gratipay is saving the state in the meta field
        # for compatibility with legacy customers
        'state': 'meta.region',
        'last4': 'number',
        'last_four': 'number',
        'card_type': 'brand',
        'expiration_month': 'expiration_month',
        'expiration_year': 'expiration_year',
    }


class BalancedBankAccount(BalancedThing):
    """This is a dict-like wrapper around a Balanced bank account.
    """

    thing_type = 'bank_account'

    keys_to_attr_paths = {
        'customer_href': 'customer.href',
    }
