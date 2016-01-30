from datetime import datetime
from decimal import Decimal


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
