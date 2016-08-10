from mangopaysdk.mangopayapi import MangoPayApi
from mangopaysdk.tools.resttool import BaseRestTool
from mangopaysdk.types.dto import Dto


class CustomRestTool(BaseRestTool):

    def _sendRequest(self, request):
        request.headers.pop('Connection', None)
        return super(CustomRestTool, self)._sendRequest(request)


mangoapi = MangoPayApi()
mangoapi.Config.RestToolClass = CustomRestTool


class NS(Dto):
    def __init__(self, **kw):
        self.__dict__.update(kw)

class PayInPaymentDetailsBankWire(NS): pass
class PayInPaymentDetailsCard(NS): pass
class PayInExecutionDetailsDirect(NS): pass
class PayOutPaymentDetailsBankWire(NS): pass
