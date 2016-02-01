from datetime import datetime, timedelta
from decimal import Decimal
from functools import partial
import hashlib
import hmac
import json
import os.path

from rx import Observable
from tornado.gen import coroutine
from tornado.httpclient import AsyncHTTPClient, HTTPRequest
from tornado.ioloop import IOLoop

from btce import config, commands, events
from btce.common import get_logger, normalize_value, FIRST_CURRENCY_PLACES, SECOND_CURRENCY_PLACES
from btce.models import Order
from btce.utils import u, r


logger = get_logger(__name__)


def _get_currency_pair():
    return '%s_%s' % (config.FIRST_CURRENCY, config.SECOND_CURRENCY)


class _PublicApiConnector:

    API_URL = config.EXCHANGE_SITE + '/api/3'

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

    API_URL = config.EXCHANGE_SITE + '/tapi'

    ORDER_TYPE_SELL = 'sell'
    ORDER_TYPE_BUY = 'buy'

    def __init__(self, currency_pair, key, secret):
        self._currency_pair = currency_pair
        self._key = key
        self._secret = secret
        self._http_client = AsyncHTTPClient()
        self._nonce_keeper = _NonceKeeper()

    @coroutine
    def _try_make_request(self, count, *args, **kwargs):
        try:
            return (yield self._make_request(*args, **kwargs))
        except Exception as e:
            count += 1
            if count >= 20:
                raise Exception('cannot make request after %s tries: %s' % (count, e))
            if not count % 5:
                logger.warning('Cannot make request even after %s tries: %s', count, e)
            return (yield self._try_make_request(count, *args, **kwargs))

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
            'nonce': self._nonce_keeper.get(),
        })
        return '&'.join('%s=%s' % item for item in params.items())

    @coroutine
    def get_balance(self):
        response = yield self._try_make_request(0, 'getInfo')
        return dict((key, Decimal(value)) for key, value in response['funds'].items())

    @coroutine
    def create_order(self, order_type, amount, price):
        response = yield self._try_make_request(0, 'Trade', {
            'pair': _get_currency_pair(),
            'type': order_type,
            'rate': str(price),
            'amount': str(amount),
        })
        return dict((key, Decimal(value)) for key, value in response['funds'].items())

    @coroutine
    def get_active_orders(self):
        response = yield self._try_make_request(0, 'ActiveOrders')
        return ({
            'id': order_id,
            'type': data['type'],
            'amount': Decimal(data['amount']),
            'price': Decimal(data['rate']),
            'created': datetime.utcfromtimestamp(data['timestamp_created']),
        } for order_id, data in response.items() if data['pair'] == self._currency_pair)

    @coroutine
    def cancel_order(self, order_id):
        response = yield self._try_make_request(0, 'CancelOrder', {'order_id': order_id})
        return dict((key, Decimal(value)) for key, value in response['funds'].items())


class _NonceKeeper:

    def get(self):
        store_file = os.path.join(config.DATA_DIR, 'nonce')
        with open(store_file, 'r') as store:
            nonce = int(store.read())
            nonce += 1
        with open(store_file, 'w') as store:
            store.write(str(nonce))
        return nonce


class RealExchange:

    def __init__(self, event_stream: Observable, command_stream: Observable):
        self._public_api = _PublicApiConnector(_get_currency_pair())
        self._trade_api = _TradeApiConnector(_get_currency_pair(), config.API_KEY, config.API_SECRET)
        self._event_stream = event_stream
        self._command_stream = command_stream

    def init(self):
        self._subscribe_for_sell_order_command()
        self._subscribe_for_buy_order_command()
        self._subscribe_for_cancel_order_command()
        self._run()

    def _subscribe_for_sell_order_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.CreateSellOrderCommand))
            .map(lambda command: r(command.amount, command.price))
            .subscribe(u(self._create_sell_order)))

    @coroutine
    def _create_sell_order(self, amount, price):
        logger.debug('Creating sell order (%s for %s)', amount, price)
        try:
            yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_SELL, amount, price)
        except Exception as e:
            logger.debug('Cannot create sell order: %s', e)

    def _subscribe_for_buy_order_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.CreateBuyOrderCommand))
            .map(lambda command: r(command.amount, command.price))
            .subscribe(u(self._create_buy_order)))

    @coroutine
    def _create_buy_order(self, amount, price):
        logger.debug('Creating buy order (%s for %s)', amount, price)
        try:
            yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_BUY, amount, price)
        except Exception as e:
            logger.debug('Cannot create buy order: %s', e)

    def _subscribe_for_cancel_order_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.CancelOrderCommand))
            .map(lambda command: command.order_id)
            .subscribe(self._cancel_order))

    @coroutine
    def _cancel_order(self, order_id):
        logger.debug('Cancelling order %s', order_id)
        try:
            yield self._trade_api.cancel_order(order_id)
        except Exception as e:
            logger.debug('Cannot cancel order: %s', e)

    def _run(self):
        ioloop = IOLoop.instance()
        ioloop.add_callback(partial(self._request_all_data, ioloop))
        ioloop.add_callback(partial(self._request_active_orders, ioloop))
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
        except Exception as e:
            logger.warn('Cannot get server time: %s', e)
        else:
            self._event_stream.on_next(events.TimeEvent(server_time))

    @coroutine
    def _request_price(self):
        try:
            price = yield self._public_api.get_price()
        except Exception as e:
            logger.warn('Cannot get price: %s', e)
        else:
            self._event_stream.on_next(events.PriceEvent(normalize_value(price, SECOND_CURRENCY_PLACES)))

    @coroutine
    def _request_balance(self):
        try:
            balance = yield self._trade_api.get_balance()

        except Exception as e:
            logger.warn('Cannot get balance: %s', e)
        else:
            first_currency_amount = normalize_value(balance[config.FIRST_CURRENCY], FIRST_CURRENCY_PLACES)
            self._event_stream.on_next(events.FirstCurrencyBalanceEvent(first_currency_amount))
            second_currency_amount = normalize_value(balance[config.SECOND_CURRENCY], SECOND_CURRENCY_PLACES)
            self._event_stream.on_next(events.SecondCurrencyBalanceEvent(second_currency_amount))

    @coroutine
    def _request_active_orders(self, ioloop):
        try:
            orders = yield self._trade_api.get_active_orders()
            orders = sorted((Order(order['id'], Order.TYPE_SELL if order['type'] == 'sell' else Order.TYPE_BUY,
                                   normalize_value(order['amount'], FIRST_CURRENCY_PLACES),
                                   normalize_value(order['price'], SECOND_CURRENCY_PLACES), order['created'])
                             for order in orders), key=lambda order: order.price)
        except Exception as e:
            logger.warn('Cannot get active orders: %s', e)
        else:
            self._event_stream.on_next(events.ActiveOrdersEvent(orders))
        ioloop.add_timeout(timedelta(hours=3), partial(self._request_active_orders, ioloop))
