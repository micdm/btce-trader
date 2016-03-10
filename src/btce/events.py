from datetime import datetime
from decimal import Decimal

from btce.config import CurrencyPair, Currency
from typing import Sequence

from btce.models import Order


class _Event:
    pass


class TimeEvent(_Event):

    def __init__(self, value: datetime):
        self.value = value


class BalanceEvent(_Event):

    def __init__(self, currency: Currency, value: Decimal):
        self.currency = currency
        self.value = value


class PriceEvent(_Event):

    def __init__(self, pair: CurrencyPair, value: Decimal):
        self.pair = pair
        self.value = value


class ActiveOrdersEvent(_Event):

    def __init__(self, pair: CurrencyPair, orders: Sequence[Order]):
        self.pair = pair
        self.orders = orders
