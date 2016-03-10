from decimal import Decimal

from btce.config import Currency, CurrencyPair


class _Command:
    pass


class GetServerTimeCommand(_Command):
    pass


class GetPriceCommand(_Command):

    def __init__(self, pair: CurrencyPair):
        self.pair = pair


class GetBalanceCommand(_Command):

    def __init__(self, currency: Currency):
        self.currency = currency


class GetActiveOrdersCommand(_Command):

    def __init__(self, pair: CurrencyPair):
        self.pair = pair


class _CreateOrderCommand(_Command):

    def __init__(self, currency: Currency, amount: Decimal, price: Decimal):
        self.currency = currency
        self.amount = amount
        self.price = price


class CreateSellOrderCommand(_CreateOrderCommand):
    pass


class CreateBuyOrderCommand(_CreateOrderCommand):
    pass


class CancelOrderCommand(_Command):

    def __init__(self, order_id: str):
        self.order_id = order_id
