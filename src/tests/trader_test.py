from unittest import TestCase

from mox3.mox import Mox
from rx.subjects import Subject

from btce.common import FirstCurrencyBalance, SecondCurrencyBalance
from btce.trader import Trader
from btce.utils.utils import r
from tests.utils import use_dataproviders, dataprovider, test_stream


@use_dataproviders
class TraderTest(TestCase):

    def setUp(self):
        self._mox = Mox()
        self._trader = Trader(None, None, None, None)

    def tearDown(self):
        self._mox.UnsetStubs()

    def provider_get_balance_with_change_stream():
        return (
            ((FirstCurrencyBalance(100),), ((100, 0),)),
            ((FirstCurrencyBalance(100), FirstCurrencyBalance(200)), ((100, 0), (200, 100))),
            ((FirstCurrencyBalance(100), SecondCurrencyBalance(100), FirstCurrencyBalance(200)), ((100, 0), (200, 100))),
        )

    @dataprovider(provider_get_balance_with_change_stream)
    def test_get_balance_with_change_stream(self, data, expected):
        subject = Subject()
        result = test_stream(subject, self._trader._get_balance_with_change_stream(subject, FirstCurrencyBalance), data)
        self.assertEqual(result, expected)

    def provider_get_distinct_balance_stream():
        return (
            ((100,), ((100,),)),
            ((100, 200), ((100,), (200,),)),
            ((100, 100), ((100,),)),
        )

    @dataprovider(provider_get_distinct_balance_stream)
    def test_get_distinct_balance_stream(self, data, expected):
        subject = Subject()
        result = test_stream(subject, self._trader._get_distinct_balance_stream(subject), data)
        self.assertEqual(result, expected)

    def provider_get_distinct_jumping_price_stream():
        return (
            ((100,), ()),
            ((100, 101), ()),
            ((100, 200), ((200,),)),
            ((100, 200, 200), ((200,),)),
        )

    @dataprovider(provider_get_distinct_jumping_price_stream)
    def test_get_distinct_jumping_price_stream(self, data, expected):
        subject = Subject()
        result = test_stream(subject, self._trader._get_distinct_jumping_price_stream(subject), data)
        self.assertEqual(result, expected)

    def provider_get_distinct_price_and_balance_stream():
        return (
            (({0: 100}), ()),
            (({0: 100}, {1: r(100, 0)}), ((100, 100),)),
            (({0: 100}, {1: r(100, 0)}, {0: 200}), ((100, 100), (100, 200))),
            (({0: 100}, {1: r(100, 0)}, {0: 200}, {1: r(200, 100)}), ((100, 100), (100, 200))),
        )

    @dataprovider(provider_get_distinct_price_and_balance_stream)
    def test_get_distinct_price_and_balance_stream(self, data, expected):
        subjects = Subject(), Subject()
        result = test_stream(subjects, self._trader._get_distinct_price_and_balance_stream(*subjects), data)
        self.assertEqual(result, expected)

    def provider_get_distinct_positive_balance_and_price_stream():
        return (
            (({0: r(100, 10)}), ()),
            (({0: r(100, 10)}, {1: 100}), ((100, 100),)),
            (({0: r(100, 10)}, {1: 100}, {0: r(90, -10)}), ((100, 100),)),
            (({0: r(100, 10)}, {1: 100}, {0: r(110, 10)}), ((100, 100), (110, 100))),
            (({0: r(100, 10)}, {1: 100}, {0: r(110, 10)}, {1: 200}), ((100, 100), (110, 100))),
        )

    @dataprovider(provider_get_distinct_positive_balance_and_price_stream)
    def test_get_distinct_positive_balance_and_price_stream(self, data, expected):
        subjects = Subject(), Subject()
        result = test_stream(subjects, self._trader._get_distinct_positive_balance_and_price_stream(*subjects), data)
        self.assertEqual(result, expected)

    def test_get_random_margin_jitter(self):
        for i in range(1000000):
            value = self._trader._get_random_margin_jitter(1)
            self.assertGreaterEqual(value, -1)
            self.assertLessEqual(value, 1)
