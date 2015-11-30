from datetime import timedelta
from decimal import Decimal

from btce import config
from btce.common import normalize_value, FIRST_CURRENCY_PLACES, SECOND_CURRENCY_PLACES, get_logger, SellOrder, \
    BuyOrder, FirstCurrencyBalance, SecondCurrencyBalance
from btce.utils.utils import u, r


logger = get_logger(__name__)


class Trader:

    REASON_PERIODIC = 0
    REASON_BALANCE_CHANGED = 1

    def __init__(self, time_stream, price_stream, balance_stream, order_stream):
        self._time_stream = time_stream
        self._balance_stream = balance_stream
        self._price_stream = price_stream
        self._order_stream = order_stream

    def init(self):
        first_currency_balance_stream = self._get_balance_with_change_stream(self._balance_stream, FirstCurrencyBalance)
        second_currency_balance_stream = self._get_balance_with_change_stream(self._balance_stream, SecondCurrencyBalance)
        self._log_time_and_price(self._time_stream, self._price_stream)
        self._log_balance(first_currency_balance_stream, second_currency_balance_stream)
        self._create_orders_when_price_jumps(self._price_stream, first_currency_balance_stream, second_currency_balance_stream)
        self._create_orders_when_balance_changes(first_currency_balance_stream, second_currency_balance_stream)

    def _get_balance_with_change_stream(self, stream, balance_class):
        return (stream
            .filter(
                lambda balance: isinstance(balance, balance_class)
            )
            .map(
                lambda balance: balance.amount
            )
            .scan(u(
                lambda prev, change, balance: r(balance, balance - prev if prev is not None else Decimal(0))
            ), r(None, None)))

    def _log_time_and_price(self, time_stream, price_stream):
        stream = self._get_distinct_time_and_price_stream(time_stream, price_stream)
        stream.subscribe(u(
            lambda time, price: logger.info('Time now is %s, price is %s', time, price)
        ))

    def _get_distinct_time_and_price_stream(self, time_stream, price_stream):
        return (time_stream
            .scan(
                lambda prev, time: prev if prev and time - prev < timedelta(minutes=10) else time
            )
            .combine_latest(price_stream,
                lambda time, price: r(time, price)
            )
            .distinct_until_changed(u(
                lambda time, price: time
            )))

    def _log_balance(self, first_currency_balance_stream, second_currency_balance_stream):
        stream = self._get_distinct_balance_stream(first_currency_balance_stream)
        stream.subscribe(u(
            lambda balance, change: logger.info('First currency balance is %s (%s)', balance, change)
        ))
        stream = self._get_distinct_balance_stream(second_currency_balance_stream)
        stream.subscribe(u(
            lambda balance, change: logger.info('Second currency balance is %s (%s)', balance, change)
        ))

    def _get_distinct_balance_stream(self, balance_stream):
        return (balance_stream
            .distinct_until_changed())

    def _create_orders_when_price_jumps(self, price_stream, first_currency_balance_stream, second_currency_balance_stream):
        price_stream = self._get_distinct_jumping_price_stream(price_stream)
        stream = self._get_distinct_price_and_balance_stream(price_stream, first_currency_balance_stream)
        stream.subscribe(u(
            lambda balance, price: self._create_sell_order(balance, price, self.REASON_PERIODIC)
        ))
        stream = self._get_distinct_price_and_balance_stream(price_stream, second_currency_balance_stream)
        stream.subscribe(u(
            lambda balance, price: self._create_buy_order(balance, price, self.REASON_PERIODIC)
        ))

    def _get_distinct_jumping_price_stream(self, price_stream):
        return (price_stream
            .scan(
                lambda prev, price: prev if prev and abs(price - prev) / prev < 0.05 else price
            )
            .distinct_until_changed()
            .skip(1))

    def _get_distinct_price_and_balance_stream(self, price_stream, balance_stream):
        return (price_stream
            .combine_latest(balance_stream, u(
                lambda price, balance, change: r(balance, price)
            ))
            .distinct_until_changed(u(
                lambda balance, price: price
            )))

    def _create_orders_when_balance_changes(self, first_currency_balance_stream, second_currency_balance_stream):
        stream = self._get_distinct_positive_balance_and_price_stream(first_currency_balance_stream, self._price_stream)
        stream.subscribe(u(
            lambda balance, price: self._create_sell_order(balance, price, self.REASON_BALANCE_CHANGED)
        ))
        stream = self._get_distinct_positive_balance_and_price_stream(second_currency_balance_stream, self._price_stream)
        stream.subscribe(u(
            lambda balance, price: self._create_buy_order(balance, price, self.REASON_BALANCE_CHANGED)
        ))

    def _get_distinct_positive_balance_and_price_stream(cls, balance_stream, price_stream):
        return (balance_stream
            .filter(u(
                lambda balance, change: change > 0
            ))
            .combine_latest(price_stream, u(
                lambda balance, change, price: r(balance, price)
            ))
            .distinct_until_changed(u(
                lambda balance, price: balance
            )))

    def _create_sell_order(self, balance, price, reason):
        new_price = normalize_value(price + price * config.MARGIN, SECOND_CURRENCY_PLACES)
        amount = config.DEAL_AMOUNT or max(balance, config.MIN_AMOUNT)
        logger.info('Create sell order: price is %s, new price is %s, reason is %s', price, new_price, reason)
        if amount <= balance:
            self._order_stream.on_next(SellOrder(amount, new_price))
        else:
            logger.info('Not enough funds for sell')

    def _create_buy_order(self, balance, price, reason):
        new_price = normalize_value(price - price * config.MARGIN, SECOND_CURRENCY_PLACES)
        amount = config.DEAL_AMOUNT or max(config.MIN_AMOUNT, normalize_value(balance / new_price,
                                                                              FIRST_CURRENCY_PLACES))
        logger.info('Create buy order: price is %s, new price is %s, reason is %s', price, new_price, reason)
        if amount <= balance / new_price:
            self._order_stream.on_next(BuyOrder(amount, new_price))
        else:
            logger.info('Not enough funds for buy')
