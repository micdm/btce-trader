from datetime import datetime, timedelta
from decimal import Decimal

from btce.config import TradingOptions, CurrencyPair
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
from btce.common import get_logger, normalize_value
from btce.models import Order
from btce.utils import u, r


logger = get_logger(__name__)


def _currency_pair_to_string(pair: CurrencyPair):
    return '%s_%s' % (pair.first.name.lower(), pair.second.name.lower())


class _PublicApiConnector:

    API_URL = config.EXCHANGE_SITE + '/api/3'

    def __init__(self):
        self._http_client = AsyncHTTPClient()

    @coroutine
    def _make_request(self, method, pair):
        response = yield self._http_client.fetch('%s/%s/%s' % (self.API_URL, method, pair))
        return json.loads(response.body.decode())

    @coroutine
    def get_price(self, pair):
        response = yield self._make_request('ticker', pair)
        return Decimal(response[pair]['last'])


class _TradeApiConnector:

    API_URL = config.EXCHANGE_SITE + '/tapi'

    ORDER_TYPE_SELL = 'sell'
    ORDER_TYPE_BUY = 'buy'

    def __init__(self, key, secret):
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
    def get_balance(self, currency):
        response = yield self._try_make_request(0, 'getInfo')
        return Decimal(response['funds'][currency.name.lower()])

    @coroutine
    def create_order(self, order_type, pair, amount, price):
        yield self._try_make_request(0, 'Trade', {
            'pair': pair,
            'type': order_type,
            'rate': str(price),
            'amount': str(amount),
        })

    @coroutine
    def get_active_orders(self, pair):
        response = yield self._try_make_request(0, 'ActiveOrders')
        return ({
            'id': order_id,
            'type': data['type'],
            'amount': Decimal(data['amount']),
            'price': Decimal(data['rate']),
            'created': datetime.utcfromtimestamp(data['timestamp_created']),
        } for order_id, data in response.items() if data['pair'] == pair)

    @coroutine
    def cancel_order(self, order_id):
        yield self._try_make_request(0, 'CancelOrder', {'order_id': order_id})


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
        self._public_api = _PublicApiConnector()
        self._trade_api = _TradeApiConnector(config.API_KEY, config.API_SECRET)
        self._event_stream = event_stream
        self._command_stream = command_stream

    def init(self):
        self._subscribe_for_get_server_time_command()
        self._subscribe_for_get_price_command()
        self._subscribe_for_get_balance_command()
        self._subscribe_for_get_active_orders_command()
        self._subscribe_for_sell_order_command()
        self._subscribe_for_buy_order_command()
        self._subscribe_for_cancel_order_command()
        IOLoop.instance().start()

    def _subscribe_for_get_server_time_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.GetServerTimeCommand))
            .debounce(1000)
            .subscribe(lambda command: self._get_server_time()))

    @coroutine
    def _get_server_time(self):
        server_time = datetime.utcnow()
        self._event_stream.on_next(events.TimeEvent(server_time))

    def _subscribe_for_get_price_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.GetPriceCommand))
            .subscribe(lambda command: self._get_price(command.pair)))

    @coroutine
    def _get_price(self, pair):
        try:
            price = yield self._public_api.get_price(_currency_pair_to_string(pair))
        except Exception as e:
            logger.warn('Cannot get price: %s', e)
        else:
            self._event_stream.on_next(events.PriceEvent(pair, normalize_value(price, pair.second.places)))

    def _subscribe_for_get_balance_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.GetBalanceCommand))
            .subscribe(lambda command: self._get_balance(command.currency)))

    @coroutine
    def _get_balance(self, currency):
        try:
            balance = yield self._trade_api.get_balance(currency)
        except Exception as e:
            logger.warn('Cannot get balance: %s', e)
        else:
            amount = normalize_value(balance[currency.name.lower()], currency.places)
            self._event_stream.on_next(events.BalanceEvent(currency, amount))

    def _subscribe_for_get_active_orders_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.GetActiveOrdersCommand))
            .subscribe(lambda command: self._get_active_orders(command.pair)))

    @coroutine
    def _get_active_orders(self, pair):
        try:
            orders = yield self._trade_api.get_active_orders(_currency_pair_to_string(pair))
            orders = sorted((Order(order['id'], Order.TYPE_SELL if order['type'] == 'sell' else Order.TYPE_BUY,
                                   normalize_value(order['amount'], pair.first.places),
                                   normalize_value(order['price'], pair.second.places), order['created'])
                             for order in orders), key=lambda order: order.price)
        except Exception as e:
            logger.warn('Cannot get active orders: %s', e)
        else:
            self._event_stream.on_next(events.ActiveOrdersEvent(orders))

    def _subscribe_for_sell_order_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.CreateSellOrderCommand))
            .subscribe(lambda command: self._create_sell_order(command.pair, command.amount, command.price)))

    @coroutine
    def _create_sell_order(self, pair, amount, price):
        logger.debug('Creating sell order (%s%s for %s%s)', amount, pair.first, price, pair.second)
        try:
            yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_SELL, _currency_pair_to_string(pair), amount, price)
        except Exception as e:
            logger.debug('Cannot create sell order: %s', e)

    def _subscribe_for_buy_order_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.CreateBuyOrderCommand))
            .subscribe(lambda command: self._create_buy_order(command.pair, command.amount, command.price)))

    @coroutine
    def _create_buy_order(self, pair, amount, price):
        logger.debug('Creating buy order (%s%s for %s%s)', amount, pair.first, price, pair.second)
        try:
            yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_BUY, _currency_pair_to_string(pair), amount, price)
        except Exception as e:
            logger.debug('Cannot create buy order: %s', e)

    def _subscribe_for_cancel_order_command(self):
        (self._command_stream
            .filter(lambda command: isinstance(command, commands.CancelOrderCommand))
            .subscribe(lambda command: self._cancel_order(command.order_id)))

    @coroutine
    def _cancel_order(self, order_id):
        logger.debug('Cancelling order %s', order_id)
        try:
            yield self._trade_api.cancel_order(order_id)
        except Exception as e:
            logger.debug('Cannot cancel order: %s', e)
