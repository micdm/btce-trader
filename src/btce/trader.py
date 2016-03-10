from datetime import timedelta, datetime
from decimal import Decimal
from random import uniform

from rx import Observable

from btce import config, commands, events
from btce.config import TradingOptions
from btce.common import normalize_value, get_logger
from btce.utils import u, r


logger = get_logger(__name__)


class Trader:

    REASON_PRICE_JUMP = 0
    REASON_BALANCE_CHANGE = 1

    def __init__(self, options: TradingOptions, event_stream: Observable, command_stream: Observable):
        self._options = options
        self._event_stream = event_stream
        self._command_stream = command_stream

    def __str__(self):
        return str(self._options.pair)

    def init(self):
        time_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.TimeEvent))
            .map(lambda event: event.value))
        price_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.PriceEvent))
            .filter(lambda event: event.pair == self._options.pair)
            .map(lambda event: event.value))
        first_currency_balance_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.BalanceEvent))
            .filter(lambda event: event.currency == self._options.pair.first)
            .map(lambda event: event.value)
            .scan(u(lambda prev, change, balance: r(balance, balance - prev if prev is not None else Decimal(0))),
                  r(None, None)))
        second_currency_balance_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.BalanceEvent))
            .filter(lambda event: event.currency == self._options.pair.second)
            .map(lambda event: event.value)
            .scan(u(lambda prev, change, balance: r(balance, balance - prev if prev is not None else Decimal(0))),
                  r(None, None)))
        active_order_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.ActiveOrdersEvent))
            .filter(lambda event: event.pair == self._options.pair)
            .map(lambda event: event.orders))
        self._get_server_time()
        self._get_price()
        self._log_time_and_price(time_stream, price_stream)
        self._log_balance(first_currency_balance_stream, second_currency_balance_stream)
        self._log_active_orders(active_order_stream)
        self._create_orders_when_price_jumps(price_stream, first_currency_balance_stream,
                                             second_currency_balance_stream)
        self._create_orders_when_balance_changes(price_stream, first_currency_balance_stream,
                                                 second_currency_balance_stream)
        self._cancel_outdated_orders(active_order_stream)

    def _get_server_time(self):
        (Observable
            .timer(1, 1000)
            .subscribe(lambda count: self._command_stream.on_next(commands.GetServerTimeCommand())))

    def _get_price(self):
        (Observable
            .timer(1, 5000)
            .subscribe(lambda count: self._command_stream.on_next(commands.GetPriceCommand(self._options.pair))))

    def _log_time_and_price(self, time_stream, price_stream):
        (time_stream
            #.scan(lambda prev, time: prev if prev and time - prev < timedelta(minutes=10) else time)
            .combine_latest(price_stream, lambda time, price: r(time, price))
            #.distinct_until_changed(u(lambda time, price: time))
            .subscribe(u(lambda time, price: logger.info('%s Time now is %s, price is %s', self, time, price))))

    def _log_balance(self, first_currency_balance_stream, second_currency_balance_stream):
        (first_currency_balance_stream
            .distinct_until_changed()
            .subscribe(u(lambda balance, change: logger.info('%s First currency balance is %s (%s)', self, balance,
                                                             change))))
        (second_currency_balance_stream
            .distinct_until_changed()
            .subscribe(u(lambda balance, change: logger.info('%s Second currency balance is %s (%s)', self, balance,
                                                             change))))

    def _log_active_orders(self, active_order_stream):
        (active_order_stream
            .subscribe(lambda orders: logger.debug('%s Active orders: %s', self, ', '.join(map(repr, orders))) if orders
                                      else logger.debug('%s No active orders found', self)))

    def _create_orders_when_price_jumps(self, price_stream, first_currency_balance_stream,
                                        second_currency_balance_stream):
        jumping_price_stream = (price_stream
            .scan(lambda prev, price: prev if prev and abs(price - prev) / prev < self._options.price_jump_value else price)
            .distinct_until_changed()
            .skip(1))
        (jumping_price_stream
            .combine_latest(first_currency_balance_stream, u(lambda price, balance, change: r(balance, price)))
            .distinct_until_changed(u(lambda balance, price: price))
            .subscribe(u(lambda balance, price: self._create_sell_order(balance, price, self.REASON_PRICE_JUMP))))
        (jumping_price_stream
            .combine_latest(second_currency_balance_stream, u(lambda price, balance, change: r(balance, price)))
            .distinct_until_changed(u(lambda balance, price: price))
            .subscribe(u(lambda balance, price: self._create_buy_order(balance, price, self.REASON_PRICE_JUMP))))

    def _create_orders_when_balance_changes(self, price_stream, first_currency_balance_stream,
                                            second_currency_balance_stream):
        (first_currency_balance_stream
            .filter(u(lambda balance, change: change > 0))
            .combine_latest(price_stream, u(lambda balance, change, price: r(balance, price)))
            .distinct_until_changed(u(lambda balance, price: balance))
            .subscribe(u(lambda balance, price: self._create_sell_order(balance, price, self.REASON_BALANCE_CHANGE))))
        (second_currency_balance_stream
            .filter(u(lambda balance, change: change > 0))
            .combine_latest(price_stream, u(lambda balance, change, price: r(balance, price)))
            .distinct_until_changed(u(lambda balance, price: balance))
            .subscribe(u(lambda balance, price: self._create_buy_order(balance, price, self.REASON_BALANCE_CHANGE))))

    def _create_sell_order(self, balance, price, reason):
        margin = self._options.margin + self._get_random_margin_jitter(self._options.margin_jitter)
        new_price = normalize_value(price + price * margin, self._options.pair.second.places)
        amount = self._options.deal_amount or max(balance, self._options.min_amount)
        logger.info('%s Create sell order: price is %s, new price is %s (margin is %s), reason is %s', self, price,
                    new_price, margin, reason)
        if amount <= balance:
            self._command_stream.on_next(commands.CreateSellOrderCommand(self._options.pair, amount, new_price))
        else:
            logger.info('%s Not enough funds for sell', self)

    def _create_buy_order(self, balance, price, reason):
        margin = self._options.margin + self._get_random_margin_jitter(self._options.margin_jitter)
        new_price = normalize_value(price - price * margin, self._options.pair.second.places)
        amount = self._options.deal_amount or max(self._options.min_amount,
                                                  normalize_value(balance / new_price, self._options.pair.first.places))
        logger.info('%s Create buy order: price is %s, new price is %s (margin is %s), reason is %s', self, price,
                    new_price, margin, reason)
        if amount <= balance / new_price:
            self._command_stream.on_next(commands.CreateBuyOrderCommand(self._options.pair, amount, new_price))
        else:
            logger.info('%s Not enough funds for buy', self)

    def _get_random_margin_jitter(self, jitter):
        return normalize_value(Decimal(uniform(-float(jitter), float(jitter))), 4)

    def _cancel_outdated_orders(self, active_order_stream):
        (active_order_stream
            .select_many(lambda orders: Observable.from_iterable(orders))
            .filter(lambda order: datetime.utcnow() - order.created > config.ORDER_OUTDATE_PERIOD)
            .subscribe(self._cancel_order))

    def _cancel_order(self, order):
        logger.info('%s Cancel outdated order %s (%s) created %s (%s ago)', self, order.order_id, order, order.created,
                    datetime.utcnow() - order.created)
        self._command_stream.on_next(commands.CancelOrderCommand(order.order_id))
