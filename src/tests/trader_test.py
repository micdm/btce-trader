from collections import namedtuple
from unittest import TestCase

from mox3.mox import Mox
from rx.subjects import Subject

from btce.trader import Trader
from btce.utils import r


class TraderTest(TestCase):

    def setUp(self):
        self._mox = Mox()
        self._trader = Trader(None, None, None)

    def tearDown(self):
        self._mox.UnsetStubs()

    def test_create_sell_order_when_price_jumps(self):
        trader = Trader(namedtuple('TradingOptions', 'price_jump_value')(price_jump_value=0.05), None, None)
        price_stream, first_currency_balance_stream, second_currency_balance_stream = Subject(), Subject(), Subject()
        self._mox.StubOutWithMock(trader, '_create_sell_order')
        trader._create_sell_order(100, 1000, Trader.REASON_PRICE_JUMP)
        self._mox.ReplayAll()
        trader._create_orders_when_price_jumps(price_stream, first_currency_balance_stream,
                                               second_currency_balance_stream)
        price_stream.on_next(100)
        price_stream.on_next(1000)
        first_currency_balance_stream.on_next(r(100, 100))
        self._mox.VerifyAll()

    def test_create_buy_order_when_price_jumps(self):
        trader = Trader(namedtuple('TradingOptions', 'price_jump_value')(price_jump_value=0.05), None, None)
        price_stream, first_currency_balance_stream, second_currency_balance_stream = Subject(), Subject(), Subject()
        self._mox.StubOutWithMock(trader, '_create_buy_order')
        trader._create_buy_order(100, 1000, Trader.REASON_PRICE_JUMP)
        self._mox.ReplayAll()
        trader._create_orders_when_price_jumps(price_stream, first_currency_balance_stream,
                                               second_currency_balance_stream)
        price_stream.on_next(100)
        price_stream.on_next(1000)
        second_currency_balance_stream.on_next(r(100, 100))
        self._mox.VerifyAll()

    def test_create_sell_order_when_balance_changes(self):
        price_stream, first_currency_balance_stream, second_currency_balance_stream = Subject(), Subject(), Subject()
        self._mox.StubOutWithMock(self._trader, '_create_sell_order')
        self._trader._create_sell_order(100, 100, Trader.REASON_BALANCE_CHANGE)
        self._mox.ReplayAll()
        self._trader._create_orders_when_balance_changes(price_stream, first_currency_balance_stream,
                                                     second_currency_balance_stream)
        first_currency_balance_stream.on_next(r(100, 100))
        price_stream.on_next(100)
        self._mox.VerifyAll()

    def test_create_buy_order_when_balance_changes(self):
        price_stream, first_currency_balance_stream, second_currency_balance_stream = Subject(), Subject(), Subject()
        self._mox.StubOutWithMock(self._trader, '_create_buy_order')
        self._trader._create_buy_order(100, 100, Trader.REASON_BALANCE_CHANGE)
        self._mox.ReplayAll()
        self._trader._create_orders_when_balance_changes(price_stream, first_currency_balance_stream,
                                                     second_currency_balance_stream)
        second_currency_balance_stream.on_next(r(100, 100))
        price_stream.on_next(100)
        self._mox.VerifyAll()

    def test_get_random_margin_jitter(self):
        for i in range(100000):
            value = self._trader._get_random_margin_jitter(1)
            self.assertGreaterEqual(value, -1)
            self.assertLessEqual(value, 1)
