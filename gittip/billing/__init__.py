"""This module encapsulates billing logic and db access.

There are three pieces of information for each participant related to billing:

    balanced_customer_href
        * NULL - This participant has never been billed.
        * 'deadbeef' - This participant has had a Balanced account created for
          them, either by adding a credit card or a bank account.
    last_bill_result
        * NULL - This participant has not had their credit card charged yet.
        * '' - This participant has a working card.
        * <message> - An error message.
    last_ach_result
        * NULL - This participant has not wired up a bank account yet.
        * '' - This participant has a working bank account.
        * <message> - An error message.

"""
from __future__ import unicode_literals

import balanced
import stripe
from aspen.utils import typecheck


def get_balanced_account(db, username, balanced_customer_href):
    """Find or create a balanced.Account.
    """
    typecheck( username, unicode
             , balanced_customer_href, (unicode, None)
              )

    if balanced_customer_href is None:
        customer = balanced.Customer(meta={
            'username': username,
        }).save()
        BALANCED_ACCOUNT = """\

                UPDATE participants
                   SET balanced_customer_href=%s
                 WHERE username=%s

        """
        db.run(BALANCED_ACCOUNT, (customer.href, username))
    else:
        customer = balanced.Customer.fetch(balanced_customer_href)
    return customer


def associate(db, thing, username, balanced_customer_href, balanced_thing_uri):
    """Given four unicodes, return a unicode.

    This function attempts to associate the credit card or bank account details
    referenced by balanced_thing_uri with a Balanced Account. If it fails we
    log and return a unicode describing the failure. Even for failure we keep
    balanced_customer_href; we don't reset it to None/NULL. It's useful for
    loading the previous (bad) info from Balanced in order to prepopulate the
    form.

    """
    typecheck( username, unicode
               , balanced_customer_href, (unicode, None, balanced.Customer)
               , balanced_thing_uri, unicode
               , thing, unicode
              )

    if isinstance(balanced_customer_href, balanced.Customer):
        balanced_account = balanced_customer_href
    else:
        balanced_account = get_balanced_account( db
                                               , username
                                               , balanced_customer_href
                                                )
    invalidate_on_balanced(thing, balanced_account.href)
    SQL = "UPDATE participants SET last_%s_result=%%s WHERE username=%%s"
    try:
        if thing == "credit card":
            SQL %= "bill"
            obj = balanced.Card.fetch(balanced_thing_uri)
            #add = balanced_account.add_card

        else:
            assert thing == "bank account", thing # sanity check
            SQL %= "ach"
            obj = balanced.BankAccount.fetch(balanced_thing_uri)
            #add = balanced_account.add_bank_account

        obj.associate_to_customer(balanced_account)
    except balanced.exc.HTTPError as err:
        error = err.message.message.decode('UTF-8')  # XXX UTF-8?
    else:
        error = ''
    typecheck(error, unicode)

    db.run(SQL, (error, username))
    return error


def invalidate_on_balanced(thing, balanced_customer_href):
    """XXX Things in balanced cannot be deleted at the moment.

    Instead we mark all valid cards as invalid which will restrict against
    anyone being able to issue charges against them in the future.

    See: https://github.com/balanced/balanced-api/issues/22

    """
    assert thing in ("credit card", "bank account")
    typecheck(balanced_customer_href, (str, unicode))

    customer = balanced.Customer.fetch(balanced_customer_href)
    things = customer.cards if thing == "credit card" else customer.bank_accounts

    for _thing in things:
        _thing.unstore()


def clear(db, thing, username, balanced_customer_href):
    typecheck( thing, unicode
             , username, unicode
             , balanced_customer_href, (unicode, str)
              )
    assert thing in ("credit card", "bank account"), thing
    invalidate_on_balanced(thing, balanced_customer_href)
    CLEAR = """\

        UPDATE participants
           SET last_%s_result=NULL
         WHERE username=%%s

    """ % ("bill" if thing == "credit card" else "ach")
    db.run(CLEAR, (username,))


def store_error(db, thing, username, msg):
    typecheck(thing, unicode, username, unicode, msg, unicode)
    assert thing in ("credit card", "bank account"), thing
    ERROR = """\

        UPDATE participants
           SET last_%s_result=%%s
         WHERE username=%%s

    """ % ("bill" if thing == "credit card" else "ach")
    db.run(ERROR, (msg, username))


# Card
# ====
# While we're migrating data we need to support loading data from both Stripe
# and Balanced.

class StripeCard(object):
    """This is a dict-like wrapper around a Stripe PaymentMethod.
    """

    _customer = None  # underlying stripe.Customer object

    def __init__(self, stripe_customer_id):
        """Given a Stripe customer id, load data from Stripe.
        """
        if stripe_customer_id is not None:
            self._customer = stripe.Customer.retrieve(stripe_customer_id)

    def _get(self, name, default=""):
        """Given a name, return a string.
        """
        out = ""
        if self._customer is not None:
            out = self._customer.get('active_card', {}).get(name, "")
            if out is None:
                out = default
        return out

    def __getitem__(self, name):
        """Given a name, return a string.
        """
        if name == 'id':
            out = self._customer.id if self._customer is not None else None
        elif name == 'last4':
            out = self._get('last4')
            if out:
                out = "************" + out
        else:
            name = { 'address_1': 'address_line1'
                   , 'address_2': 'address_line2'
                   , 'state': 'address_state'
                   , 'zip': 'address_zip'
                    }.get(name, name)
            out = self._get(name)
        return out


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
        # gittip is saving the state in the meta field
        # for compatibility with legacy customers
        'state': 'meta.region',
        'last4': 'number',
        'last_four': 'number',
    }


class BalancedBankAccount(BalancedThing):
    """This is a dict-like wrapper around a Balanced bank account.
    """

    thing_type = 'bank_account'

    keys_to_attr_paths = {
        'customer_href': 'customer.href',
    }
