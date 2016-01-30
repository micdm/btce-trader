from decimal import Decimal


class _Command:
    pass


class _CreateOrderCommand(_Command):

    def __init__(self, amount: Decimal, price: Decimal):
        self.amount = amount
        self.price = price


class CreateSellOrderCommand(_CreateOrderCommand):
    pass


class CreateBuyOrderCommand(_CreateOrderCommand):
    pass


class CancelOrderCommand(_Command):

    def __init__(self, order_id: str):
        self.order_id = order_id
