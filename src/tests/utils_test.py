from unittest import TestCase

from btce.utils import get_data_packed


class UtilsTest(TestCase):

    def test_get_data_packed(self):
        data = get_data_packed(foo=1, bar=2)
        self.assertEqual(data.foo, 1)
        self.assertEqual(data.bar, 2)

    def test_get_data_packed_if_factory(self):
        factory = get_data_packed('foo', 'bar')
        data = factory(1, 2)
        self.assertEqual(data.foo, 1)
        self.assertEqual(data.bar, 2)

    def test_get_data_packed_if_factory_and_packed_params(self):
        factory = get_data_packed('foo', 'bar')
        data = factory(get_data_packed(foo=1), 2)
        self.assertEqual(data.foo, 1)
        self.assertEqual(data.bar, 2)

    def test_get_data_packed_if_factory_and_packed_params_and_cannot_match(self):
        factory = get_data_packed('foo', 'bar')
        self.assertRaises(Exception, factory, get_data_packed(baz=1), 2)
