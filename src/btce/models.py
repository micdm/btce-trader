from datetime import datetime
from decimal import Decimal


class Order:

    TYPE_SELL = 0
    TYPE_BUY = 1

    def __init__(self, order_id: str, order_type: int, amount: Decimal, price: Decimal, created: datetime):
        self.order_id = order_id
        self.order_type = order_type
        self.amount = amount
        self.price = price
        self.created = created

    def __repr__(self):
        return '%s %s for %s' % ('sell' if self.order_type == self.TYPE_SELL else 'buy', self.amount, self.price)
