from datetime import datetime
from decimal import Decimal


class Currency:

    def __init__(self, name, places):
        self.name = name
        self.places = places

    def __str__(self):
        return self.name


class CurrencyPair:

    def __init__(self, first, second):
        self.first = first
        self.second = second

    def __str__(self):
        return '%s/%s' % (self.first, self.second)


class TradingOptions:

    def __init__(self, pair: CurrencyPair, margin, margin_jitter, min_amount,
                 deal_amount, price_jump_value):
        self.pair = pair
        self.margin = margin
        self.margin_jitter = margin_jitter
        self.min_amount = min_amount
        self.deal_amount = deal_amount or min_amount
        self.price_jump_value = price_jump_value


class Order:

    TYPE_SELL = 0
    TYPE_BUY = 1

    def __init__(self, order_id: str, order_type: int, amount: Decimal, price: Decimal, created: datetime,
                 completed: datetime):
        self.order_id = order_id
        self.order_type = order_type
        self.amount = amount
        self.price = price
        self.created = created
        self.completed = completed

    def __repr__(self):
        return 'Order(type=%s,amount=%s,price=%s)' % ('sell' if self.order_type == self.TYPE_SELL else 'buy', self.amount, self.price)
