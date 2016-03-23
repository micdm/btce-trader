from datetime import datetime
from decimal import Decimal
import hashlib
import hmac
import json
import os.path

from rx import Observable
from rx.disposables import CompositeDisposable
from tornado.concurrent import TracebackFuture
from tornado.curl_httpclient import CurlAsyncHTTPClient
from tornado.gen import coroutine
from tornado.httpclient import HTTPRequest
from tornado.ioloop import IOLoop

from btce import config, commands, events
from btce.common import get_logger, normalize_value
from btce.models import CurrencyPair, Order, CURRENCIES

logger = get_logger(__name__)


def _currency_pair_to_string(pair: CurrencyPair):
    return '%s_%s' % (pair.first.name.lower(), pair.second.name.lower())


class _PublicApiConnector:

    API_URL = config.EXCHANGE_SITE + '/api/3'

    def __init__(self):
        self._http_client = CurlAsyncHTTPClient()

    @coroutine
    def _make_request(self, method, pair):
        response = yield self._http_client.fetch('%s/%s/%s' % (self.API_URL, method, pair))
        return json.loads(response.body.decode())

    @coroutine
    def get_price(self, pair):
        response = yield self._make_request('ticker', pair)
        return Decimal(response[pair]['last'])


class _RequestQueue:

    TRY_MAX_COUNT = 5

    def __init__(self, request_handler):
        self._queue = []
        self._is_working = False
        self._request_handler = request_handler

    def put(self, *args):
        future = TracebackFuture()
        self._queue.append((args, future, 1))
        if not self._is_working:
            self._execute_next_request()
        return future

    @coroutine
    def _execute_next_request(self):
        self._is_working = True
        request, future, try_count = self._queue.pop(0)
        try:
            result = yield self._request_handler(*request)
            future.set_result(result)
        except Exception as e:
            try_count += 1
            if try_count > self.TRY_MAX_COUNT:
                logger.warn('Cannot execute request after %s tries: %s', self.TRY_MAX_COUNT, e)
                future.set_exception(e)
            else:
                self._queue.append((request, future, try_count))
        self._is_working = False
        if self._queue:
            self._execute_next_request()


class _TradeApiConnector:

    API_URL = config.EXCHANGE_SITE + '/tapi'

    ORDER_TYPE_SELL = 'sell'
    ORDER_TYPE_BUY = 'buy'

    def __init__(self, key, secret):
        self._key = key
        self._secret = secret
        self._http_client = CurlAsyncHTTPClient(max_clients=1)
        self._nonce_keeper = _NonceKeeper()
        self._request_queue = _RequestQueue(self._make_request)

    @coroutine
    def _add_request(self, method, params=None):
        return (yield self._request_queue.put(method, params))

    @coroutine
    def _make_request(self, method, params=None):
        request_body = self._get_request_body(method, params or {})
        sign = hmac.new(self._secret.encode(), request_body.encode(), hashlib.sha512).hexdigest()
        request = HTTPRequest(self.API_URL, method='POST', headers={'Key': self._key, 'Sign': sign}, body=request_body)
        response = yield self._http_client.fetch(request)
        response_body = json.loads(response.body.decode())
        if response_body.get('success'):
            return response_body['return'], None
        return None, response_body['error']

    def _get_request_body(self, method, params):
        params.update({
            'method': method,
            'nonce': self._nonce_keeper.get(),
        })
        return '&'.join('%s=%s' % item for item in params.items())

    @coroutine
    def get_balance(self, currency):
        result, error = yield self._add_request('getInfo')
        if error is not None:
            raise Exception('cannot make request: %s' % error)
        return Decimal(result['funds'][currency])

    @coroutine
    def create_order(self, order_type, pair, amount, price):
        result, error = yield self._add_request('Trade', {
            'pair': pair,
            'type': order_type,
            'rate': str(price),
            'amount': str(amount),
        })
        if error is not None:
            raise Exception('cannot make request: %s' % error)
        return dict((currency, Decimal(value)) for currency, value in result['funds'].items())

    @coroutine
    def get_active_orders(self, pair):
        result, error = yield self._add_request('ActiveOrders', {'pair': pair})
        if error is not None:
            if error == 'no orders':
                return ()
            raise Exception('cannot make request: %s' % error)
        return ({
            'id': order_id,
            'type': data['type'],
            'amount': Decimal(data['amount']),
            'price': Decimal(data['rate']),
            'created': datetime.utcfromtimestamp(data['timestamp_created']),
        } for order_id, data in result.items())

    @coroutine
    def get_completed_orders(self, pair):
        result, error = yield self._add_request('TradeHistory', {'pair': pair, 'count': 20})
        if error is not None:
            if error == 'no trades':
                return ()
            raise Exception('cannot make request: %s' % error)
        return ({
            'id': data['order_id'],
            'type': data['type'],
            'amount': Decimal(data['amount']),
            'price': Decimal(data['rate']),
            'completed': datetime.utcfromtimestamp(data['timestamp']),
        } for data in result.values())

    @coroutine
    def cancel_order(self, order_id):
        result, error = yield self._add_request('CancelOrder', {'order_id': order_id})
        if error is not None:
            raise Exception('cannot make request: %s' % error)
        return dict((currency, Decimal(value)) for currency, value in result['funds'].items())


class _NonceKeeper:

    def get(self):
        store_file = os.path.join(config.DATA_DIR, 'nonce')
        with open(store_file, 'r') as store:
            nonce = int(store.read())
            nonce += 1
        with open(store_file, 'w') as store:
            store.write(str(nonce))
        return nonce


class ExchangeConnector:

    def __init__(self, events: Observable, commands: Observable):
        self._subscription = None
        self._public_api = _PublicApiConnector()
        self._trade_api = _TradeApiConnector(config.API_KEY, config.API_SECRET)
        self._events = events
        self._commands = commands

    def __repr__(self):
        return 'ExchangeConnector()'

    def init(self):
        logger.info('Starting %s', self)
        self._subscription = CompositeDisposable(
            self._subscribe_for_get_server_time_command(),
            self._subscribe_for_get_price_command(),
            self._subscribe_for_get_balance_command(),
            self._subscribe_for_get_active_orders_command(),
            self._subscribe_for_get_completed_orders_command(),
            self._subscribe_for_create_sell_order_command(),
            self._subscribe_for_create_buy_order_command(),
            self._subscribe_for_cancel_order_command(),
        )

    def run(self):
        IOLoop.instance().start()

    def _subscribe_for_get_server_time_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.GetServerTimeCommand))
            .subscribe(lambda command: self._get_server_time()))

    def _subscribe_for_get_price_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.GetPriceCommand))
            .subscribe(lambda command: self._get_price(command.pair)))

    def _subscribe_for_get_balance_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.GetBalanceCommand))
            .subscribe(lambda command: self._get_balance(command.currency)))

    def _subscribe_for_get_active_orders_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.GetActiveOrdersCommand))
            .subscribe(lambda command: self._get_active_orders(command.pair)))

    def _subscribe_for_get_completed_orders_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.GetCompletedOrdersCommand))
            .subscribe(lambda command: self._get_completed_orders(command.pair)))

    def _subscribe_for_create_sell_order_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.CreateSellOrderCommand))
            .subscribe(lambda command: self._create_sell_order(command.pair, command.amount, command.price)))

    def _subscribe_for_create_buy_order_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.CreateBuyOrderCommand))
            .subscribe(lambda command: self._create_buy_order(command.pair, command.amount, command.price)))

    def _subscribe_for_cancel_order_command(self):
        return (self._commands
            .filter(lambda command: isinstance(command, commands.CancelOrderCommand))
            .subscribe(lambda command: self._cancel_order(command.order_id)))

    @coroutine
    def _get_server_time(self):
        server_time = datetime.utcnow()
        self._events.on_next(events.TimeEvent(server_time))

    @coroutine
    def _get_price(self, pair):
        try:
            price = yield self._public_api.get_price(_currency_pair_to_string(pair))
        except Exception as e:
            logger.warn('Cannot get price: %s', e)
        else:
            self._events.on_next(events.PriceEvent(pair, normalize_value(price, pair.second.places)))

    @coroutine
    def _get_balance(self, currency):
        try:
            balance = yield self._trade_api.get_balance(currency.name.lower())
        except Exception as e:
            logger.warn('Cannot get balance: %s', e)
        else:
            amount = normalize_value(balance, currency.places)
            self._events.on_next(events.BalanceEvent(currency, amount))

    @coroutine
    def _get_active_orders(self, pair):
        try:
            orders = yield self._trade_api.get_active_orders(_currency_pair_to_string(pair))
            orders = sorted((Order(int(order['id']), Order.TYPE_SELL if order['type'] == 'sell' else Order.TYPE_BUY,
                                   normalize_value(order['amount'], pair.first.places),
                                   normalize_value(order['price'], pair.second.places), order['created'], None)
                             for order in orders), key=lambda order: order.price)
        except Exception as e:
            logger.warn('Cannot get active orders: %s', e)
        else:
            self._events.on_next(events.ActiveOrdersEvent(pair, orders))

    @coroutine
    def _get_completed_orders(self, pair):
        try:
            orders = yield self._trade_api.get_completed_orders(_currency_pair_to_string(pair))
            orders = sorted((Order(int(order['id']), Order.TYPE_SELL if order['type'] == 'sell' else Order.TYPE_BUY,
                                   normalize_value(order['amount'], pair.first.places),
                                   normalize_value(order['price'], pair.second.places), None, order['completed'])
                             for order in orders), key=lambda order: order.completed, reverse=True)
        except Exception as e:
            logger.warn('Cannot get completed orders: %s', e)
        else:
            self._events.on_next(events.CompletedOrdersEvent(pair, orders))

    @coroutine
    def _create_sell_order(self, pair, amount, price):
        logger.debug('Creating sell order (%s %s for %s %s)', amount, pair.first, price, pair.second)
        try:
            balance = yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_SELL,
                                                         _currency_pair_to_string(pair), amount, price)
        except Exception as e:
            logger.debug('Cannot create sell order: %s', e)
        else:
            self._send_balance_events(balance)

    @coroutine
    def _create_buy_order(self, pair, amount, price):
        logger.debug('Creating buy order (%s %s for %s %s)', amount, pair.first, price, pair.second)
        try:
            balance = yield self._trade_api.create_order(_TradeApiConnector.ORDER_TYPE_BUY, _currency_pair_to_string(pair), amount, price)
        except Exception as e:
            logger.debug('Cannot create buy order: %s', e)
        else:
            self._send_balance_events(balance)

    @coroutine
    def _cancel_order(self, order_id):
        logger.debug('Cancelling order %s', order_id)
        try:
            balance = yield self._trade_api.cancel_order(order_id)
        except Exception as e:
            logger.debug('Cannot cancel order: %s', e)
        else:
            self._send_balance_events(balance)

    def _send_balance_events(self, balance):
        for currency in CURRENCIES:
            amount = balance.get(currency.name.lower())
            if amount is not None:
                self._commands.on_next(events.BalanceEvent(currency, normalize_value(amount, currency.places)))

    def deinit(self):
        logger.info('Stopping %s', self)
        if self._subscription is not None:
            self._subscription.dispose()
