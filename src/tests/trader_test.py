from decimal import Decimal
from unittest import TestCase

from mox3.mox import Mox
from rx.subjects import Subject

from btce import events
from btce.trader import Trader
from btce.utils import get_data_packed as d
from tests.utils import test_stream, dataprovider, use_dataproviders


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
        events = Subject()
        trader = Trader(None, events, None)
        result = test_stream(trader._get_balance('currency'), events.on_next, input_data)
        self.assertEqual(result, expected)
