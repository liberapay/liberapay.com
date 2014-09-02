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
from aspen.utils import typecheck

from gratipay.models.participant import Participant


def store_result(db, thing, username, new_result):
    """Update the participant's last_{ach,bill}_result in the DB.

    Also update receiving amounts of the participant's tippees.
    """
    assert thing in ("credit card", "bank account"), thing
    x = "bill" if thing == "credit card" else "ach"

    # Update last_thing_result in the DB
    SQL = """

        UPDATE participants p
           SET last_{0}_result=%s
         WHERE username=%s
     RETURNING is_suspicious
             , ( SELECT last_{0}_result
                   FROM participants p2
                  WHERE p2.id = p.id
               ) AS old_result

    """.format(x)
    p = db.one(SQL, (new_result, username))

    # Update the receiving amounts of tippees if necessary
    if thing != "credit card":
        return
    if p.is_suspicious or new_result == p.old_result:
        return
    with db.get_cursor() as cursor:
        Participant.from_username(username).update_giving(cursor)
        tippees = cursor.all("""
            SELECT tippee
              FROM current_tips
             WHERE tipper=%(tipper)s;
        """, dict(tipper=username))
        for tippee in tippees:
            Participant.from_username(tippee).update_receiving(cursor)


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
    try:
        if thing == "credit card":
            obj = balanced.Card.fetch(balanced_thing_uri)
        else:
            assert thing == "bank account", thing # sanity check
            obj = balanced.BankAccount.fetch(balanced_thing_uri)
        obj.associate_to_customer(balanced_account)
    except balanced.exc.HTTPError as err:
        error = err.message.message.decode('UTF-8')  # XXX UTF-8?
    else:
        error = ''
    typecheck(error, unicode)

    store_result(db, thing, username, error)
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
    invalidate_on_balanced(thing, balanced_customer_href)
    store_result(db, thing, username, None)


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
