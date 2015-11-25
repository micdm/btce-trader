from datetime import datetime, timedelta
from decimal import Decimal
import json
from time import time

from functools import partial
import hashlib
import hmac
from tornado.gen import coroutine
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.ioloop import IOLoop

from btce import config
from btce.common import BuyOrder, SellOrder, get_logger, normalize_value, FIRST_CURRENCY_PLACES, FirstCurrencyBalance, \
    SecondCurrencyBalance, SECOND_CURRENCY_PLACES
from btce.exchange.base import Exchange

logger = get_logger(__name__)


def _get_currency_pair():
    return '%s_%s' % (config.FIRST_CURRENCY, config.SECOND_CURRENCY)


class _PublicApiConnector:

    API_URL = 'https://btc-e.com/api/3'

    def __init__(self, currency_pair):
        self._currency_pair = currency_pair
        self._http_client = AsyncHTTPClient()

    @coroutine
    def _make_request(self, method):
        response = yield self._http_client.fetch('%s/%s/%s' % (self.API_URL, method, self._currency_pair))
        return json.loads(response.body.decode())

    @coroutine
    def get_time(self):
        response = yield self._make_request('info')
        return datetime.utcfromtimestamp(response['server_time'])

    @coroutine
    def get_price(self):
        response = yield self._make_request('ticker')
        return Decimal(response[self._currency_pair]['last'])


class _TradeApiConnector:

    API_URL = 'https://btc-e.com/tapi'

    ORDER_TYPE_SELL = 'sell'
    ORDER_TYPE_BUY = 'buy'

    def __init__(self, currency_pair, key, secret):
        self._currency_pair = currency_pair
        self._key = key
        self._secret = secret
        self._http_client = AsyncHTTPClient()

    @coroutine
    def _make_request(self, method, params=None):
        request_body = self._get_request_body(method, params or {})
        sign = hmac.new(self._secret.encode(), request_body.encode(), hashlib.sha512).hexdigest()
        request = HTTPRequest(self.API_URL, method='POST', headers={'Key': self._key, 'Sign': sign}, body=request_body)
        response = yield self._http_client.fetch(request)
        response_body = json.loads(response.body.decode())
        if response_body.get('success'):
            return response_body['return']
        raise Exception('cannot make request: %s' % response_body.get('error'))

    def _get_request_body(self, method, params):
        params.update({
            'method': method,
            'nonce': int(time()),
        })
        return '&'.join('%s=%s' % item for item in params.items())

    @coroutine
    def get_balance(self):
        response = yield self._make_request('getInfo')
        return dict((key, Decimal(value)) for key, value in response['funds'].items())

    @coroutine
    def create_order(self, order_type, amount, price):
        response = yield self._make_request('Trade', {
            'pair': _get_currency_pair(),
            'type': order_type,
            'rate': str(price),
            'amount': str(amount),
        })
        return dict((key, Decimal(value)) for key, value in response['funds'].items())


class RealExchange(Exchange):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._public_api = _PublicApiConnector(_get_currency_pair())
        self._trade_api = _TradeApiConnector(_get_currency_pair(), config.API_KEY, config.API_SECRET)

    def init(self):
        self._subscribe_for_sell_order()
        self._subscribe_for_buy_order()
        self._run()

    def _subscribe_for_sell_order(self):
        (self._order_stream
            .filter(lambda order: isinstance(order, SellOrder))
            .subscribe(self._create_sell_order))

    def _subscribe_for_buy_order(self):
        (self._order_stream
            .filter(lambda order: isinstance(order, BuyOrder))
            .subscribe(self._create_buy_order))

    @coroutine
    def _create_sell_order(self, order):
        logger.debug('Creating sell order %s', order)
        try:
            balance = yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_SELL, order.amount, order.price)
        except Exception as e:
            logger.debug('Cannot create sell order: %s', e)
        else:
            self._update_balance(balance)

    @coroutine
    def _create_buy_order(self, order):
        logger.debug('Creating buy order %s', order)
        try:
            balance = yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_BUY, order.amount, order.price)
        except Exception as e:
            logger.debug('Cannot create buy order: %s', e)
        else:
            self._update_balance(balance)

    def _run(self):
        ioloop = IOLoop.instance()
        ioloop.add_callback(partial(self._request_all_data, ioloop))
        ioloop.start()

    def _request_all_data(self, ioloop):
        self._request_server_time()
        self._request_price()
        self._request_balance()
        ioloop.add_timeout(timedelta(seconds=3), partial(self._request_all_data, ioloop))

    @coroutine
    def _request_server_time(self):
        try:
            server_time = yield self._public_api.get_time()
            self._time_stream.on_next(server_time)
        except Exception as e:
            logger.warn('Cannot get server time: %s', e)

    @coroutine
    def _request_price(self):
        try:
            price = yield self._public_api.get_price()
            self._price_stream.on_next(normalize_value(price, SECOND_CURRENCY_PLACES))
        except Exception as e:
            logger.warn('Cannot get price: %s', e)

    @coroutine
    def _request_balance(self):
        try:
            balance = yield self._trade_api.get_balance()
            self._update_balance(balance)
        except Exception as e:
            logger.warn('Cannot get balance: %s', e)

    def _update_balance(self, balance):
        first_currency_amount = normalize_value(balance[config.FIRST_CURRENCY], FIRST_CURRENCY_PLACES)
        self._balance_stream.on_next(FirstCurrencyBalance(first_currency_amount))
        second_currency_amount = normalize_value(balance[config.SECOND_CURRENCY], SECOND_CURRENCY_PLACES)
        self._balance_stream.on_next(SecondCurrencyBalance(second_currency_amount))
