from mangopaysdk.mangopayapi import MangoPayApi
from mangopaysdk.types.dto import Dto

mangoapi = MangoPayApi()

class NS(Dto):
    def __init__(self, **kw):
        self.__dict__.update(kw)

class PayInPaymentDetailsBankWire(NS): pass
class PayInPaymentDetailsCard(NS): pass
class PayInExecutionDetailsDirect(NS): pass
class PayOutPaymentDetailsBankWire(NS): pass
