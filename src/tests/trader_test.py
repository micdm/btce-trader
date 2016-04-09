from decimal import Decimal
import operator
from unittest import TestCase

from mox3.mox import Mox
from rx import Observable

from btce import events
from btce.models import Order, TradingOptions, CurrencyPair, CURRENCY_BTC, CURRENCY_USD
from btce.trader import Trader
from btce.utils import get_data_packed as d
from tests.utils import dataprovider, use_dataproviders


@use_dataproviders
class TraderTest(TestCase):

    def setUp(self):
        self._mox = Mox()

    def tearDown(self):
        self._mox.ResetAll()

    @staticmethod
    def provider_get_balance():
        return (
            (('event',), None),
            ((events.BalanceEvent('currency', 'value'),), d(balance='value', change=Decimal(0))),
            ((events.BalanceEvent('currency', 1), events.BalanceEvent('currency', 2)), d(balance=2, change=1)),
        )

    @dataprovider('provider_get_balance')
    def test_get_balance(self, input_data, expected):
        trader = Trader(None, None, None)
        result = list(trader._get_balance(Observable.from_iterable(input_data), 'currency').to_blocking())
        self.assertEqual(result[-1] if result else None, expected)

    @staticmethod
    def provider_get_completed_orders_singly():
        return (
            (('event',), None),
            ((events.CompletedOrdersEvent('pair', (1,)), events.CompletedOrdersEvent('pair', (1,))), None),
            ((events.CompletedOrdersEvent('pair', (1,)), events.CompletedOrdersEvent('pair', (1, 2, 3))), 3),
        )

    @dataprovider('provider_get_completed_orders_singly')
    def test_get_completed_orders_singly(self, input_data, expected):
        trader = Trader(None, None, None)
        result = list(trader._get_completed_orders_singly(Observable.from_iterable(input_data), 'pair').to_blocking())
        self.assertEqual(result[-1] if result else None, expected)

    @staticmethod
    def provider_get_new_orders():
        return (
            ((1,), None),
            ((3,), d(order_type='order_type', amount=3, price='price')),
        )

    @dataprovider('provider_get_new_orders')
    def test_get_new_orders(self, input_data, expected):
        trader = Trader(None, None, None)
        self._mox.StubOutWithMock(trader, '_get_type_and_amount_and_price_for_new_order')
        for amount in input_data:
            trader._get_type_and_amount_and_price_for_new_order(amount).AndReturn(('order_type', amount, 'price'))
        self._mox.ReplayAll()
        result = list(trader._get_new_orders(Observable.from_iterable(input_data), 2).to_blocking())
        self.assertEqual(result[-1] if result else None, expected)
        self._mox.VerifyAll()

    @staticmethod
    def provider_get_new_price():
        return (
            (Order.TYPE_SELL, operator.gt),
            (Order.TYPE_BUY, operator.lt),
        )

    @dataprovider('provider_get_new_price')
    def test_get_new_price(self, order_type, compare_function):
        options = TradingOptions(CurrencyPair(CURRENCY_BTC, CURRENCY_USD), 1, 1, None, None, None)
        trader = Trader(options, None, None)
        price = trader._get_new_price(order_type, 100)
        self.assertTrue(compare_function(price, 100))
