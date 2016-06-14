from datetime import datetime
from decimal import Decimal

from typing import Optional


class Currency:

    def __init__(self, name: str, places: int):
        self.name = name
        self.places = places

    def __str__(self):
        return self.name


CURRENCY_BTC = Currency('BTC', 6)
CURRENCY_LTC = Currency('LTC', 5)
CURRENCY_NVC = Currency('NVC', 3)
CURRENCY_NMC = Currency('NMC', 3)
CURRENCY_PPC = Currency('PPC', 5)
CURRENCY_ETH = Currency('ETH', 5)
CURRENCY_USD = Currency('USD', 3)
CURRENCIES = (CURRENCY_BTC, CURRENCY_LTC, CURRENCY_NVC, CURRENCY_NMC, CURRENCY_PPC, CURRENCY_ETH, CURRENCY_USD)


class CurrencyPair:

    def __init__(self, first: Currency, second: Currency):
        self.first = first
        self.second = second

    def __str__(self):
        return '%s/%s' % (self.first, self.second)

    def __iter__(self):
        return self.first, self.second


class TradingOptions:

    def __init__(self, pair: CurrencyPair, margin, margin_jitter, min_amount,
                 deal_amount, price_jump_value):
        self.pair = pair
        self.margin = margin
        self.margin_jitter = margin_jitter
        self.min_amount = min_amount
        self.deal_amount = deal_amount
        self.price_jump_value = price_jump_value


class Order:

    TYPE_SELL = 0
    TYPE_BUY = 1

    def __init__(self, order_id: int, order_type: int, amount: Decimal, price: Decimal, created: Optional[datetime],
                 completed: Optional[datetime]):
        self.id = order_id
        self.type = order_type
        self.amount = amount
        self.price = price
        self.created = created
        self.completed = completed

    def __repr__(self):
        return 'Order(type=%s,amount=%s,price=%s)' % ('sell' if self.type == self.TYPE_SELL else 'buy', self.amount, self.price)

    def __hash__(self):
        return self.id

    def __eq__(self, other):
        return isinstance(other, Order) and other.id == self.id
