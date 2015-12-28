from __future__ import absolute_import, division, print_function, unicode_literals

from mangopaysdk.entities.bankaccount import BankAccount
from mangopaysdk.entities.cardregistration import CardRegistration
from mangopaysdk.entities.usernatural import UserNatural
from mangopaysdk.entities.wallet import Wallet
from mangopaysdk.types.address import Address
from mangopaysdk.types.bankaccountdetailsiban import BankAccountDetailsIBAN
import mock
import requests

from liberapay.billing import mangoapi
from liberapay.models.exchange_route import ExchangeRoute
from liberapay.testing import Harness
from liberapay.testing.vcr import use_cassette


class MangopayHarness(Harness):

    def setUp(self):
        Harness.setUp(self)
        self.david = self.make_participant(
            'david', is_suspicious=False, mangopay_user_id=self.david_id,
            mangopay_wallet_id=self.david_wallet_id, email='david@example.org'
        )
        self.janet = self.make_participant(
            'janet', is_suspicious=False, mangopay_user_id=self.janet_id,
            mangopay_wallet_id=self.janet_wallet_id, email='janet@example.net'
        )
        self.janet_route = ExchangeRoute.insert(self.janet, 'mango-cc', self.card_id)
        self.homer = self.make_participant(
            'homer', is_suspicious=False, mangopay_user_id=self.homer_id,
            mangopay_wallet_id=self.homer_wallet_id, email='homer@example.com'
        )
        self.homer_route = ExchangeRoute.insert(self.homer, 'mango-ba', self.bank_account.Id)


def fake_transfer(tr):
    tr.Status = 'SUCCEEDED'
    tr.ErrorCoce = '000000'
    tr.ErrorMessage = None
    tr.Id = -1
    return tr


class FakeTransfersHarness(Harness):

    def setUp(self):
        super(FakeTransfersHarness, self).setUp()
        self.transfer_patch = mock.patch('mangopaysdk.tools.apitransfers.ApiTransfers.Create')
        _mock = self.transfer_patch.__enter__()
        _mock.side_effect = fake_transfer
        self.transfer_mock = _mock

    def tearDown(self):
        self.transfer_patch.__exit__()
        super(FakeTransfersHarness, self).tearDown()


def make_mangopay_account(FirstName):
    account = UserNatural()
    account.FirstName = FirstName
    account.LastName = 'Foobar'
    account.CountryOfResidence = 'BE'
    account.Nationality = 'BE'
    account.Birthday = 0
    account.Email = 'nobody@example.net'
    return mangoapi.users.Create(account).Id


def make_wallet(mangopay_user_id):
    w = Wallet()
    w.Owners.append(mangopay_user_id)
    w.Description = 'test wallet'
    w.Currency = 'EUR'
    return mangoapi.wallets.Create(w)


with use_cassette('MangopayHarness'):
    cls = MangopayHarness

    cls.david_id = make_mangopay_account('David')
    cls.david_wallet_id = make_wallet(cls.david_id).Id

    cls.janet_id = make_mangopay_account('Janet')
    cls.janet_wallet_id = make_wallet(cls.janet_id).Id
    cr = CardRegistration()
    cr.UserId = cls.janet_id
    cr.Currency = 'EUR'
    cr.CardType = 'CB_VISA_MASTERCARD'
    cr = mangoapi.cardRegistrations.Create(cr)
    data = dict(
        accessKeyRef=cr.AccessKey,
        cardNumber='3569990000000132',
        cardExpirationDate='1234',
        cardCvx='123',
        data=cr.PreregistrationData,
    )
    cr.RegistrationData = requests.post(cr.CardRegistrationURL, data).text
    cr = mangoapi.cardRegistrations.Update(cr)
    cls.card_id = cr.CardId
    del cr, data

    cls.homer_id = make_mangopay_account('Homer')
    cls.homer_wallet_id = make_wallet(cls.homer_id).Id
    ba = BankAccount()
    ba.OwnerName = 'Homer Jay'
    addr = ba.OwnerAddress = Address()
    addr.AddressLine1 = 'Somewhere'
    addr.City = 'The City of Light'
    addr.PostalCode = '75001'
    addr.Country = 'FR'
    ba.Details = BankAccountDetailsIBAN()
    ba.Details.IBAN = 'FR1420041010050500013M02606'
    cls.bank_account = mangoapi.users.CreateBankAccount(cls.homer_id, ba)

    ba = BankAccount()
    ba.Type = 'IBAN'
    ba.Details = BankAccountDetailsIBAN()
    ba.Details.IBAN = 'IR861234568790123456789012'
    cls.bank_account_outside_sepa = ba
