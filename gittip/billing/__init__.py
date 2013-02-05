"""This module encapsulates billing logic and db access.

There are three pieces of information for each participant related to billing:

    balanced_account_uri    NULL - This participant has never been billed.
                            'deadbeef' - This participant has had a Balanced
                                account created for them, either by adding a
                                credit card or a bank account.
    last_bill_result        NULL - This participant has not had their credit
                                card charged yet.
                            '' - This participant has a working card.
                            <message> - An error message.
    last_ach_result         NULL - This participant has not wired up a bank
                                account yet.
                            '' - This participant has a working bank account.
                            <message> - An error message.

"""
from __future__ import unicode_literals

import gittip
import balanced
import stripe
from aspen.utils import typecheck


def get_balanced_account(participant_id, balanced_account_uri):
    """Find or create a balanced.Account.
    """
    typecheck( participant_id, unicode
             , balanced_account_uri, (unicode, None)
              )

    # XXX Balanced requires an email address
    # https://github.com/balanced/balanced-api/issues/20

    email_address = '{}@gittip.com'.format(participant_id)

    if balanced_account_uri is None:
        try:
            account = \
               balanced.Account.query.filter(email_address=email_address).one()
        except balanced.exc.NoResultFound:
            account = balanced.Account(email_address=email_address).save()
        BALANCED_ACCOUNT = """\

                UPDATE participants
                   SET balanced_account_uri=%s
                 WHERE id=%s

        """
        gittip.db.execute(BALANCED_ACCOUNT, (account.uri, participant_id))
        account.meta['participant_id'] = participant_id
        account.save()  # HTTP call under here
    else:
        account = balanced.Account.find(balanced_account_uri)
    return account


def associate(thing, participant_id, balanced_account_uri, balanced_thing_uri):
    """Given four unicodes, return a unicode.

    This function attempts to associate the credit card or bank account details
    referenced by balanced_thing_uri with a Balanced Account. If it fails we
    log and return a unicode describing the failure. Even for failure we keep
    balanced_account_uri; we don't reset it to None/NULL. It's useful for
    loading the previous (bad) info from Balanced in order to prepopulate the
    form.

    """
    typecheck( participant_id, unicode
             , balanced_account_uri, (unicode, None, balanced.Account)
             , balanced_thing_uri, unicode
             , thing, unicode
              )

    if isinstance(balanced_account_uri, balanced.Account):
        balanced_account = balanced_account_uri
    else:
        balanced_account = get_balanced_account( participant_id
                                               , balanced_account_uri
                                                )
    SQL = "UPDATE participants SET last_%s_result=%%s WHERE id=%%s"

    if thing == "credit card":
        add = balanced_account.add_card
        SQL %= "bill"
    else:
        assert thing == "bank account", thing # sanity check
        add = balanced_account.add_bank_account
        SQL %= "ach"

    try:
        add(balanced_thing_uri)
    except balanced.exc.HTTPError as err:
        error = err.message.decode('UTF-8')  # XXX UTF-8?
    else:
        error = ''
    typecheck(error, unicode)

    gittip.db.execute(SQL, (error, participant_id))
    return error


def clear(thing, participant_id, balanced_account_uri):
    typecheck( thing, unicode
             , participant_id, unicode
             , balanced_account_uri, unicode
              )
    assert thing in ("credit card", "bank account"), thing


    # XXX Things in balanced cannot be deleted at the moment.
    # =======================================================
    # Instead we mark all valid cards as invalid which will restrict against
    # anyone being able to issue charges against them in the future.
    #
    # See: https://github.com/balanced/balanced-api/issues/22

    account = balanced.Account.find(balanced_account_uri)
    things = account.cards if thing == "credit card" else account.bank_accounts

    for _thing in things:
        if _thing.is_valid:
            _thing.is_valid = False
            _thing.save()

    CLEAR = """\

        UPDATE participants
           SET last_%s_result=NULL
         WHERE id=%%s

    """ % ("bill" if thing == "credit card" else "ach")
    gittip.db.execute(CLEAR, (participant_id,))


def store_error(thing, participant_id, msg):
    typecheck(thing, unicode, participant_id, unicode, msg, unicode)
    assert thing in ("credit card", "bank account"), thing
    ERROR = """\

        UPDATE participants
           SET last_%s_result=%%s
         WHERE id=%%s

    """ % ("bill" if thing == "credit card" else "ach")
    gittip.db.execute(ERROR, (msg, participant_id))


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


class BalancedCard(object):
    """This is a dict-like wrapper around a Balanced Account.
    """

    _account = None  # underlying balanced.Account object

    def __init__(self, balanced_account_uri):
        """Given a Balanced account_uri, load data from Balanced.
        """
        if balanced_account_uri is not None:
            self._account = balanced.Account.find(balanced_account_uri)

    def _get_card(self):
        """Return the most recent card on file for this account.
        """
        # XXX Indexing is borken. See:
        # https://github.com/balanced/balanced-python/issues/10
        return self._account.cards.all()[-1]

    def _get(self, name, default=""):
        """Given a name, return a unicode.
        """
        out = None
        if self._account is not None:
            try:
                card = self._get_card()
                out = getattr(card, name, None)
            except IndexError:  # no cards associated
                pass
        if out is None:
            out = default
        return out

    def __getitem__(self, name):
        """Given a name, return a string.
        """
        if name == 'id':
            out = self._account.uri if self._account is not None else None
        elif name == 'last4':
            out = self._get('last_four')
            if out:
                out = "************" + unicode(out)
        elif name == 'address_2':
            out = self._get('meta', {}).get('address_2', '')
        elif name == 'state':
            out = self._get('region')
            if not out:
                # There's a bug in balanced where the region does get persisted
                # but doesn't make it back out. This is a workaround until such
                # time as that's fixed.
                out = self._get('meta', {}).get('region', '')
        else:
            name = { 'address_1': 'street_address'
                   , 'zip': 'postal_code'
                    }.get(name, name)
            out = self._get(name)
        return out


class BalancedBankAccount(object):
    """This is a dict-like wrapper around a Balanced Account.
    """

    _account = None  # underlying balanced.Account object
    _bank_account = None

    def __init__(self, balanced_account_uri):
        """Given a Balanced account_uri, load data from Balanced.
        """
        if not balanced_account_uri:
            return

        self._account = balanced.Account.find(balanced_account_uri)

        all_accounts = self._account.bank_accounts.all()
        valid_accounts = [a for a in all_accounts if a.is_valid]
        nvalid = len(valid_accounts)

        if nvalid == 0:
            self._bank_account = None
        elif nvalid == 1:
            self._bank_account = valid_accounts[0]
        else:
            msg = "%s has %d valid accounts"
            msg %= (balanced_account_uri, len(valid_accounts))
            raise RuntimeError(msg)

    def __getitem__(self, item):
        mapper = {
            'id': 'uri',
            'account_uri': 'account.uri',
            'bank_name': 'bank_name',
            'last_four': 'last_four',
        }
        if item not in mapper:
            raise IndexError()
        if not self._bank_account:
            return None
        # account.uri will become:
        #     tiem = getattr(self._bank_account, 'account')
        #     tiem = getattr(tiem, 'uri')
        tiem  = self._bank_account
        for vals in mapper[item].split('.'):
            tiem = getattr(tiem, vals)
        return tiem

    @property
    def is_setup(self):
        return self._bank_account is not None
