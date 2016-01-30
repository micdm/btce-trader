from datetime import datetime
from decimal import Decimal
from typing import Sequence, Dict


class _Event:
    pass


class TimeEvent(_Event):

    def __init__(self, value: datetime):
        self.value = value


class _BalanceEvent(_Event):

    def __init__(self, value: Decimal):
        self.value = value


class FirstCurrencyBalanceEvent(_BalanceEvent):
    pass


class SecondCurrencyBalanceEvent(_BalanceEvent):
    pass


class PriceEvent(_Event):

    def __init__(self, value: Decimal):
        self.value = value


class ActiveOrdersEvent(_Event):

    def __init__(self, orders: Sequence[Dict]):
        self.orders = orders
