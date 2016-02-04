from datetime import timedelta, datetime
from decimal import Decimal
from random import uniform

from rx import Observable

from btce import config, commands, events
from btce.common import normalize_value, FIRST_CURRENCY_PLACES, SECOND_CURRENCY_PLACES, get_logger
from btce.utils import u, r


logger = get_logger(__name__)


class Trader:

    REASON_PRICE_JUMP = 0
    REASON_BALANCE_CHANGE = 1

    def __init__(self, event_stream: Observable, command_stream: Observable):
        self._event_stream = event_stream
        self._command_stream = command_stream

    def init(self):
        time_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.TimeEvent))
            .map(lambda event: event.value))
        price_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.PriceEvent))
            .map(lambda event: event.value))
        first_currency_balance_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.FirstCurrencyBalanceEvent))
            .map(lambda event: event.value)
            .scan(u(lambda prev, change, balance: r(balance, balance - prev if prev is not None else Decimal(0))),
                  r(None, None)))
        second_currency_balance_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.SecondCurrencyBalanceEvent))
            .map(lambda event: event.value)
            .scan(u(lambda prev, change, balance: r(balance, balance - prev if prev is not None else Decimal(0))),
                  r(None, None)))
        active_order_stream = (self._event_stream
            .filter(lambda event: isinstance(event, events.ActiveOrdersEvent))
            .map(lambda event: event.orders))
        self._log_time_and_price(time_stream, price_stream)
        self._log_balance(first_currency_balance_stream, second_currency_balance_stream)
        self._log_active_orders(active_order_stream)
        self._create_orders_when_price_jumps(price_stream, first_currency_balance_stream,
                                             second_currency_balance_stream)
        self._create_orders_when_balance_changes(price_stream, first_currency_balance_stream,
                                                 second_currency_balance_stream)
        self._cancel_outdated_orders(active_order_stream)

    def _log_time_and_price(self, time_stream, price_stream):
        (time_stream
            .scan(lambda prev, time: prev if prev and time - prev < timedelta(minutes=10) else time)
            .combine_latest(price_stream, lambda time, price: r(time, price))
            .distinct_until_changed(u(lambda time, price: time))
            .subscribe(u(lambda time, price: logger.info('Time now is %s, price is %s', time, price))))

    def _log_balance(self, first_currency_balance_stream, second_currency_balance_stream):
        (first_currency_balance_stream
            .distinct_until_changed()
            .subscribe(u(lambda balance, change: logger.info('First currency balance is %s (%s)', balance, change))))
        (second_currency_balance_stream
            .distinct_until_changed()
            .subscribe(u(lambda balance, change: logger.info('Second currency balance is %s (%s)', balance, change))))

    def _log_active_orders(self, active_order_stream):
        (active_order_stream
            .subscribe(lambda orders: logger.debug('Active orders: %s' % ', '.join(map(repr, orders)))))

    def _create_orders_when_price_jumps(self, price_stream, first_currency_balance_stream,
                                        second_currency_balance_stream):
        jumping_price_stream = (price_stream
            .scan(lambda prev, price: prev if prev and abs(price - prev) / prev < config.PRICE_JUMP_VALUE else price)
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
        margin = config.MARGIN + self._get_random_margin_jitter(config.MARGIN_JITTER)
        new_price = normalize_value(price + price * margin, SECOND_CURRENCY_PLACES)
        amount = config.DEAL_AMOUNT or max(balance, config.MIN_AMOUNT)
        logger.info('Create sell order: price is %s, new price is %s (margin is %s), reason is %s', price, new_price,
                    margin, reason)
        if amount <= balance:
            self._command_stream.on_next(commands.CreateSellOrderCommand(amount, new_price))
        else:
            logger.info('Not enough funds for sell')

    def _create_buy_order(self, balance, price, reason):
        margin = config.MARGIN + self._get_random_margin_jitter(config.MARGIN_JITTER)
        new_price = normalize_value(price - price * margin, SECOND_CURRENCY_PLACES)
        amount = config.DEAL_AMOUNT or max(config.MIN_AMOUNT,
                                           normalize_value(balance / new_price, FIRST_CURRENCY_PLACES))
        logger.info('Create buy order: price is %s, new price is %s (margin is %s), reason is %s', price, new_price,
                    margin, reason)
        if amount <= balance / new_price:
            self._command_stream.on_next(commands.CreateBuyOrderCommand(amount, new_price))
        else:
            logger.info('Not enough funds for buy')

    def _get_random_margin_jitter(self, jitter):
        return normalize_value(Decimal(uniform(-float(jitter), float(jitter))), 4)

    def _cancel_outdated_orders(self, active_order_stream):
        (active_order_stream
            .select_many(lambda orders: Observable.from_iterable(orders))
            .filter(lambda order: datetime.utcnow() - order.created > config.ORDER_OUTDATE_PERIOD)
            .subscribe(self._cancel_order))

    def _cancel_order(self, order):
        logger.info('Cancel outdated order %s (%s) created %s (%s ago)', order.order_id, order, order.created,
                    datetime.utcnow() - order.created)
        self._command_stream.on_next(commands.CancelOrderCommand(order.order_id))
