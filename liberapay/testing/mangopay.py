import itertools
from unittest import mock

from mangopay.resources import (
    BankAccount, CardRegistration, NaturalUser, Wallet,
)
import requests

from liberapay.i18n.currencies import Money
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.testing import Harness
from liberapay.testing.vcr import use_cassette


class MangopayHarness(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.david = self.make_participant(
            'david', mangopay_user_id=self.david_id,
            mangopay_wallet_id=self.david_wallet_id, email='david@example.org'
        )
        self.janet = self.make_participant(
            'janet', mangopay_user_id=self.janet_id,
            mangopay_wallet_id=self.janet_wallet_id, email='janet@example.net'
        )
        self.janet_route = ExchangeRoute.insert(
            self.janet, 'mango-cc', self.card_id, 'chargeable', currency='EUR'
        )
        self.homer = self.make_participant(
            'homer', mangopay_user_id=self.homer_id,
            mangopay_wallet_id=self.homer_wallet_id, email='homer@example.com'
        )
        self.homer_route = ExchangeRoute.insert(
            self.homer, 'mango-ba', self.bank_account.Id, 'chargeable'
        )


def fake_transfer(tr):
    tr.Status = 'SUCCEEDED'
    tr.ErrorCoce = '000000'
    tr.ErrorMessage = None
    tr.Id = -1


def fake_wallet(w):
    w.Balance = Money.ZEROS[w.Currency]
    w.Id = -next(FakeTransfersHarness.wallet_id_serial)


class FakeTransfersHarness(Harness):

    wallet_id_serial = itertools.count(1000000)

    def setUp(self):
        super().setUp()
        self.transfer_patch = mock.patch('mangopay.resources.Transfer.save', autospec=True)
        _mock = self.transfer_patch.__enter__()
        _mock.side_effect = fake_transfer
        self.transfer_mock = _mock
        self.wallet_patch = mock.patch('mangopay.resources.Wallet.save', autospec=True)
        _mock = self.wallet_patch.__enter__()
        _mock.side_effect = fake_wallet
        self.wallet_mock = _mock

    def tearDown(self):
        self.transfer_patch.__exit__()
        self.wallet_patch.__exit__()
        super().tearDown()


def make_mangopay_account(FirstName):
    account = NaturalUser()
    account.FirstName = FirstName
    account.LastName = 'Foobar'
    account.CountryOfResidence = 'BE'
    account.Nationality = 'BE'
    account.Birthday = 0
    account.Email = 'nobody@example.net'
    account.save()
    return account.Id


def make_wallet(mangopay_user_id):
    w = Wallet()
    w.Owners = [mangopay_user_id]
    w.Description = 'test wallet'
    w.Currency = 'EUR'
    w.save()
    return w


def create_card(mangopay_user_id):
    cr = CardRegistration()
    cr.UserId = mangopay_user_id
    cr.Currency = 'EUR'
    cr.CardType = 'CB_VISA_MASTERCARD'
    cr.save()
    data = dict(
        accessKeyRef=cr.AccessKey,
        cardNumber='3569990000000132',
        cardExpirationDate='1234',
        cardCvx='123',
        data=cr.PreregistrationData,
    )
    cr.RegistrationData = requests.post(cr.CardRegistrationURL, data).text
    cr.save()
    return cr


with use_cassette('MangopayOAuth'):
    import mangopay
    mangopay.get_default_handler().auth_manager.get_token()


with use_cassette('MangopayHarness'):
    cls = MangopayHarness

    cls.david_id = make_mangopay_account('David')
    cls.david_wallet_id = make_wallet(cls.david_id).Id

    cls.janet_id = make_mangopay_account('Janet')
    cls.janet_wallet_id = make_wallet(cls.janet_id).Id
    cr = create_card(cls.janet_id)
    cls.card_id = cr.CardId
    del cr

    cls.homer_id = make_mangopay_account('Homer')
    cls.homer_wallet_id = make_wallet(cls.homer_id).Id
    ba = BankAccount(user_id=cls.homer_id, type='IBAN')
    ba.OwnerName = 'Homer Jay'
    ba.OwnerAddress = {
        'AddressLine1': 'Somewhere',
        'City': 'The City of Light',
        'PostalCode': '75001',
        'Country': 'FR',
    }
    ba.IBAN = 'FR1420041010050500013M02606'
    ba.save()
    cls.bank_account = ba

    ba = BankAccount()
    ba.Type = 'IBAN'
    ba.IBAN = 'IR861234568790123456789012'
    cls.bank_account_outside_sepa = ba
