from datetime import datetime, timedelta
from decimal import Decimal
from random import uniform

from rx import Observable
from rx.disposables import CompositeDisposable

from btce import config, commands, events
from btce.common import normalize_value, get_logger, MAIN_THREAD
from btce.models import TradingOptions, Order
from btce.utils import u, r

logger = get_logger(__name__)


class Trader:

    POLL_IMMEDIATELY = 1
    POLL_SERVER_TIME_INTERVAL = 1000
    POLL_PRICE_INTERVAL = 10000
    POLL_BALANCE_INTERVAL = 600000
    POLL_ACTIVE_ORDERS_INTERVAL = 3600000
    POLL_COMPLETED_ORDERS_INTERVAL = 10000
    SHOW_TIME_AND_PRICE_INTERVAL = 600000

    REASON_PRICE_JUMP = 0
    REASON_ORDER_COMPLETED = 1

    def __init__(self, options: TradingOptions, events: Observable, commands: Observable):
        self._subscription = None
        self._options = options
        self._events = events
        self._commands = commands

    def __repr__(self):
        return 'Trader(pair=%s)' % self._options.pair

    def _get_time(self):
        return (self._events
            .filter(lambda event: isinstance(event, events.TimeEvent))
            .map(lambda event: event.value))

    def _get_price(self):
        return (self._events
            .filter(lambda event: isinstance(event, events.PriceEvent))
            .filter(lambda event: event.pair == self._options.pair)
            .map(lambda event: event.value))

    def _get_balance(self, currency):
        return (self._events
            .filter(lambda event: isinstance(event, events.BalanceEvent))
            .filter(lambda event: event.currency == currency)
            .map(lambda event: event.value)
            .scan(u(lambda prev, change, balance: r(balance, balance - prev if prev is not None
                                                  else Decimal(0))), r(None, None)))

    def _get_first_currency_balance(self):
        return self._get_balance(self._options.pair.first)

    def _get_second_currency_balance(self):
        return self._get_balance(self._options.pair.second)

    def _get_active_orders(self):
        return (self._events
            .filter(lambda event: isinstance(event, events.ActiveOrdersEvent))
            .filter(lambda event: event.pair == self._options.pair)
            .map(lambda event: event.orders))

    def _get_completed_orders(self):
        return (self._events
            .filter(lambda event: isinstance(event, events.CompletedOrdersEvent))
            .filter(lambda event: event.pair == self._options.pair)
            .map(lambda event: event.orders))

    def _get_completed_orders_singly(self):
        return (self._get_completed_orders()
            .scan(u(lambda prev, change, orders: r(orders, set(orders) - set(prev) if prev is not None else {})),
                  r(None, None))
            .map(u(lambda orders, change: change))
            .switch_map(Observable.from_iterable))

    def _get_jumping_price(self):
        return (self._get_price()
            .scan(lambda prev, price: prev if prev and abs(price - prev) / prev < self._options.price_jump_value
                                      else price)
            .distinct_until_changed()
            .skip(1))

    def init(self):
        logger.info('Starting %s', self)
        self._subscription = CompositeDisposable(
            self._subscribe_for_poll_server_time(),
            self._subscribe_for_poll_price(),
            self._subscribe_for_poll_balance(),
            self._subscribe_for_poll_active_orders(),
            self._subscribe_for_poll_completed_orders(),
            self._subscribe_for_time_and_price(),
            self._subscribe_for_balance(),
            self._subscribe_for_active_orders(),
            self._subscribe_for_completed_orders(),
            self._subscribe_for_jumping_price()
        )

    def _subscribe_for_poll_server_time(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_SERVER_TIME_INTERVAL, MAIN_THREAD)
            .subscribe(lambda count: self._commands.on_next(commands.GetServerTimeCommand())))

    def _subscribe_for_poll_price(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_PRICE_INTERVAL, MAIN_THREAD)
            .subscribe(lambda count: self._commands.on_next(commands.GetPriceCommand(self._options.pair))))

    def _subscribe_for_poll_balance(self):
        return CompositeDisposable(
            (Observable
                .timer(self.POLL_IMMEDIATELY, self.POLL_BALANCE_INTERVAL, MAIN_THREAD)
                .subscribe(lambda count: self._commands.on_next(commands.GetBalanceCommand(self._options.pair.first)))),
            (Observable
                .timer(self.POLL_IMMEDIATELY, self.POLL_BALANCE_INTERVAL, MAIN_THREAD)
                .subscribe(lambda count: self._commands.on_next(commands.GetBalanceCommand(self._options.pair.second))))
        )

    def _subscribe_for_poll_active_orders(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_ACTIVE_ORDERS_INTERVAL, MAIN_THREAD)
            .subscribe(lambda count: self._commands.on_next(commands.GetActiveOrdersCommand(self._options.pair))))

    def _subscribe_for_poll_completed_orders(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_COMPLETED_ORDERS_INTERVAL, MAIN_THREAD)
            .subscribe(lambda count: self._commands.on_next(commands.GetCompletedOrdersCommand(self._options.pair))))

    def _subscribe_for_time_and_price(self):
        return (Observable
            .combine_latest(self._get_time(), self._get_price(), r)
            .throttle_first(self.SHOW_TIME_AND_PRICE_INTERVAL, MAIN_THREAD)
            .subscribe(u(lambda time, price: logger.info('[%s] Time now is %s, price is %s', self._options.pair, time,
                                                         price))))

    def _subscribe_for_balance(self):
        return (Observable
            .combine_latest(self._get_first_currency_balance(), self._get_second_currency_balance(), r)
            .distinct_until_changed(u(lambda value1, change1, value2, change2: (value1, value2)))
            .subscribe(u(lambda value1, change1, value2, change2: logger.info('[%s] Balance is %s %s (%s) and %s %s (%s)', self._options.pair, value1,
                                                                              self._options.pair.first, change1, value2, self._options.pair.second, change2))))

    def _subscribe_for_active_orders(self):
        return CompositeDisposable(
            (self._get_active_orders()
                .subscribe(lambda orders: logger.info('[%s] Active orders: %s', self._options.pair, ', '.join(map(repr, orders))) if orders
                                          else logger.info('[%s] No active orders found', self._options.pair))),
            (self._get_active_orders()
                .switch_map(Observable.from_iterable)
                .filter(lambda order: datetime.utcnow() - order.created > config.ORDER_OUTDATE_PERIOD)
                .subscribe(self._cancel_order))
        )

    def _subscribe_for_completed_orders(self):
        common = (self._get_completed_orders_singly()
            .map(lambda order: r(*self._get_type_and_amount_and_price_for_new_order(order)))
            .filter(u(lambda order_type, amount, price: amount >= self._options.min_amount)))
        return CompositeDisposable(
            (self._get_completed_orders_singly()
                .subscribe(lambda order: logger.info('[%s] %s completed', self._options.pair, order))),
            (Observable
                .combine_latest(
                    (common
                        .filter(u(lambda order_type, amount, price: order_type == Order.TYPE_SELL))
                        .map(u(lambda order_type, amount, price: r(amount, price)))),
                    (self._get_first_currency_balance()
                        .map(u(lambda balance, change: balance))),
                    r
                )
                .distinct_until_changed(u(lambda amount, price, balance: (amount, price)))
                .filter(u(lambda amount, price, balance: amount <= balance))
                .map(u(lambda amount, price, balance: r(amount, price)))
                .subscribe(u(lambda amount, price: self._create_sell_order(amount, price,
                                                                           self.REASON_ORDER_COMPLETED)))),
            (Observable
                .combine_latest(
                    (common
                        .filter(u(lambda order_type, amount, price: order_type == Order.TYPE_BUY))
                        .map(u(lambda order_type, amount, price: r(amount, price)))),
                    (self._get_second_currency_balance()
                        .map(u(lambda balance, change: balance))),
                    r
                )
                .distinct_until_changed(u(lambda amount, price, balance: (amount, price)))
                .filter(u(lambda amount, price, balance: amount * price <= balance))
                .map(u(lambda amount, price, balance: r(amount, price)))
                .subscribe(u(lambda amount, price: self._create_buy_order(amount, price,
                                                                          self.REASON_ORDER_COMPLETED))))
        )

    def _subscribe_for_jumping_price(self):
        return CompositeDisposable(
            (Observable
                .combine_latest(
                    self._get_jumping_price(),
                    self._get_first_currency_balance().map(u(lambda balance, change: balance)),
                    r
                )
                .distinct_until_changed(u(lambda price, balance: price))
                .subscribe(u(lambda price, balance: self._create_sell_order(balance, price, self.REASON_PRICE_JUMP)))),
            (Observable
                .combine_latest(
                    self._get_jumping_price(),
                    self._get_second_currency_balance().map(u(lambda balance, change: balance)),
                    r
                )
                .distinct_until_changed(u(lambda price, balance: price))
                .subscribe(u(lambda price, balance: self._create_buy_order(balance, price, self.REASON_PRICE_JUMP)))),
        )

    def _get_type_and_amount_and_price_for_new_order(self, order):
        margin = self._options.margin + self._get_random_margin_jitter(self._options.margin_jitter)
        if order.type == Order.TYPE_SELL:
            price = normalize_value(order.price - order.price * margin, self._options.pair.second.places)
            return Order.TYPE_BUY, order.amount, price
        if order.type == Order.TYPE_BUY:
            price = normalize_value(order.price + order.price * margin, self._options.pair.second.places)
            return Order.TYPE_SELL, order.amount, price
        raise Exception('unknown order type %s' % order.type)

    def _create_sell_order(self, amount, price, reason):
        logger.info('[%s] Create sell order: price is %s, reason is %s', self._options.pair, price, reason)
        self._commands.on_next(commands.CreateSellOrderCommand(self._options.pair, amount, price))

    def _create_buy_order(self, amount, price, reason):
        logger.info('[%s] Create buy order: price is %s, reason is %s', self._options.pair, price, reason)
        self._commands.on_next(commands.CreateBuyOrderCommand(self._options.pair, amount, price))

    def _get_random_margin_jitter(self, jitter):
        return normalize_value(Decimal(uniform(-float(jitter), float(jitter))), 4)

    def _cancel_order(self, order):
        logger.info('[%s] Cancel outdated order %s created %s (%s ago)', self._options.pair, order.id, order,
                    order.created, datetime.utcnow() - order.created)
        self._commands.on_next(commands.CancelOrderCommand(order.id))

    def deinit(self):
        logger.info('Stopping %s', self)
        if self._subscription is not None:
            self._subscription.dispose()
