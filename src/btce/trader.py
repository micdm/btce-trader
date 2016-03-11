from datetime import datetime
from decimal import Decimal
from random import uniform

from rx import Observable
from rx.disposables import CompositeDisposable

from btce import config, commands, events
from btce.common import normalize_value, get_logger
from btce.models import TradingOptions
from btce.utils import u, r

logger = get_logger(__name__)


class Trader:

    POLL_IMMEDIATELY = 1
    POLL_SERVER_TIME_INTERVAL = 1000
    POLL_PRICE_INTERVAL = 10000
    POLL_BALANCE_INTERVAL = 600000
    POLL_ACTIVE_ORDERS_INTERVAL = 3600000

    REASON_PRICE_JUMP = 0
    REASON_BALANCE_CHANGE = 1

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
            self._subscribe_for_time_and_price(),
            self._subscribe_for_balance(),
            self._subscribe_for_active_orders(),
            self._subscribe_for_jumping_price()
        )

    def _subscribe_for_poll_server_time(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_SERVER_TIME_INTERVAL)
            .subscribe(lambda count: self._commands.on_next(commands.GetServerTimeCommand())))

    def _subscribe_for_poll_price(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_PRICE_INTERVAL)
            .subscribe(lambda count: self._commands.on_next(commands.GetPriceCommand(self._options.pair))))

    def _subscribe_for_poll_balance(self):
        return CompositeDisposable(
            (Observable
                .timer(self.POLL_IMMEDIATELY, self.POLL_BALANCE_INTERVAL)
                .subscribe(lambda count: self._commands.on_next(commands.GetBalanceCommand(self._options.pair.first)))),
            (Observable
                .timer(self.POLL_IMMEDIATELY, self.POLL_BALANCE_INTERVAL)
                .subscribe(lambda count: self._commands.on_next(commands.GetBalanceCommand(self._options.pair.second))))
        )

    def _subscribe_for_poll_active_orders(self):
        return (Observable
            .timer(self.POLL_IMMEDIATELY, self.POLL_ACTIVE_ORDERS_INTERVAL)
            .subscribe(lambda count: self._commands.on_next(commands.GetActiveOrdersCommand(self._options.pair))))

    def _subscribe_for_time_and_price(self):
        return (Observable
            .combine_latest(self._get_time(), self._get_price(), r)
            .throttle_first(600000)
            .subscribe(u(lambda time, price: logger.info('[%s] Time now is %s, price is %s', self._options.pair, time,
                                                         price))))

    def _subscribe_for_balance(self):
        return CompositeDisposable(
            (Observable
                .combine_latest(self._get_first_currency_balance(), self._get_second_currency_balance(), r)
                .distinct_until_changed(u(lambda value1, change1, value2, change2: (value1, value2)))
                .subscribe(u(lambda value1, change1, value2, change2: logger.info('[%s] Balance is %s %s (%s) and %s %s (%s)', self._options.pair, value1,
                                                                                  self._options.pair.first, change1, value2, self._options.pair.second, change2)))),
            (Observable
                .combine_latest(
                    self._get_first_currency_balance()
                        .filter(u(lambda balance, change: change > 0))
                        .map(u(lambda balance, change: balance)),
                    self._get_price(),
                    r
                )
                .distinct_until_changed(u(lambda balance, price: balance))
                .subscribe(u(lambda balance, price: self._create_sell_order(balance, price, self.REASON_BALANCE_CHANGE)))),
            (Observable
                .combine_latest(
                    self._get_second_currency_balance()
                        .filter(u(lambda balance, change: change > 0))
                        .map(u(lambda balance, change: balance)),
                    self._get_price(),
                    r
                )
                .distinct_until_changed(u(lambda balance, price: balance))
                .subscribe(u(lambda balance, price: self._create_buy_order(balance, price, self.REASON_BALANCE_CHANGE)))),
        )

    def _subscribe_for_active_orders(self):
        return CompositeDisposable(
            (self._get_active_orders()
                .subscribe(lambda orders: logger.info('[%s] Active orders: %s', self._options.pair, ', '.join(map(repr, orders))) if orders
                                          else logger.info('[%s] No active orders found', self._options.pair))),
            (self._get_active_orders()
                .select_many(lambda orders: Observable.from_iterable(orders))
                .filter(lambda order: datetime.utcnow() - order.created > config.ORDER_OUTDATE_PERIOD)
                .subscribe(self._cancel_order))
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

    def _create_sell_order(self, balance, price, reason):
        margin = self._options.margin + self._get_random_margin_jitter(self._options.margin_jitter)
        new_price = normalize_value(price + price * margin, self._options.pair.second.places)
        amount = self._options.deal_amount or max(balance, self._options.min_amount)
        logger.info('[%s] Create sell order: price is %s, new price is %s (margin is %s), reason is %s',
                    self._options.pair, price, new_price, margin, reason)
        if amount <= balance:
            self._commands.on_next(commands.CreateSellOrderCommand(self._options.pair, amount, new_price))
        else:
            logger.info('[%s] Not enough funds for sell', self._options.pair)

    def _create_buy_order(self, balance, price, reason):
        margin = self._options.margin + self._get_random_margin_jitter(self._options.margin_jitter)
        new_price = normalize_value(price - price * margin, self._options.pair.second.places)
        amount = self._options.deal_amount or max(self._options.min_amount,
                                                  normalize_value(balance / new_price, self._options.pair.first.places))
        logger.info('[%s] Create buy order: price is %s, new price is %s (margin is %s), reason is %s',
                    self._options.pair, price, new_price, margin, reason)
        if amount <= balance / new_price:
            self._commands.on_next(commands.CreateBuyOrderCommand(self._options.pair, amount, new_price))
        else:
            logger.info('[%s] Not enough funds for buy', self._options.pair)

    def _get_random_margin_jitter(self, jitter):
        return normalize_value(Decimal(uniform(-float(jitter), float(jitter))), 4)

    def _cancel_order(self, order):
        logger.info('[%s] Cancel outdated order %s (%s) created %s (%s ago)', self._options.pair, order.order_id, order,
                    order.created, datetime.utcnow() - order.created)
        self._commands.on_next(commands.CancelOrderCommand(order.order_id))

    def deinit(self):
        logger.info('Stopping %s', self)
        if self._subscription is not None:
            self._subscription.dispose()
