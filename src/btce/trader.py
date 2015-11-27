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
        self._first_currency_balance_stream = self._get_balance_stream(balance_stream, FirstCurrencyBalance)
        self._second_currency_balance_stream = self._get_balance_stream(balance_stream, SecondCurrencyBalance)
        self._price_stream = price_stream
        self._order_stream = order_stream

    def _get_balance_stream(self, stream, balance_class):
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

    def init(self):
        self._subscribe_for_time_and_price()
        self._subscribe_for_balance()
        self._subscribe_for_periodic_sell_and_buy_with_price()
        self._subscribe_for_change_first_currency_balance()
        self._subscribe_for_change_second_currency_balance()

    def _subscribe_for_time_and_price(self):
        (self._time_stream
            .scan(
                lambda prev, time: prev if prev and time - prev < timedelta(minutes=10) else time
            )
            .combine_latest(self._price_stream,
                lambda time, price: r(time, price)
            )
            .distinct_until_changed(u(
                lambda time, price: time
            ))
            .subscribe(u(
                lambda time, price: logger.info('Time now is %s, price is %s', time, price)
            )))

    def _subscribe_for_balance(self):
        (self._first_currency_balance_stream
            .distinct_until_changed()
            .subscribe(u(
                lambda balance, change: logger.info('First currency balance is %s (%s)', balance, change)
            )))
        (self._second_currency_balance_stream
            .distinct_until_changed()
            .subscribe(u(
                lambda balance, change: logger.info('Second currency balance is %s (%s)', balance, change)
            )))

    def _subscribe_for_periodic_sell_and_buy_with_price(self):
        stream = (self._price_stream
            .scan(
                lambda prev, price: prev if prev and abs(price - prev) / prev < 0.05 else price
            )
            .distinct_until_changed()
            .skip(1))
        (stream
            .combine_latest(self._first_currency_balance_stream, u(
                lambda price, balance, change: r(balance, price)
            ))
            .distinct_until_changed(u(
                lambda balance, price: price
            ))
            .subscribe(u(
                lambda balance, price: self._create_sell_order(balance, price, self.REASON_PERIODIC)
            )))
        (stream
            .combine_latest(self._second_currency_balance_stream, u(
                lambda price, balance, change: r(balance, price)
            ))
            .distinct_until_changed(u(
                lambda balance, price: price
            ))
            .subscribe(u(
                lambda balance, price: self._create_buy_order(balance, price, self.REASON_PERIODIC)
            )))

    def _subscribe_for_change_first_currency_balance(self):
        (self._first_currency_balance_stream
            .filter(u(
                lambda balance, change: change > 0
            ))
            .combine_latest(self._price_stream, u(
                lambda balance, change, price: r(balance, price)
            ))
            .distinct_until_changed(u(
                lambda balance, price: balance
            ))
            .subscribe(u(
                lambda balance, price: self._create_sell_order(balance, price, self.REASON_BALANCE_CHANGED)
            )))

    def _subscribe_for_change_second_currency_balance(self):
        (self._second_currency_balance_stream
            .filter(u(
                lambda balance, change: change > 0
            ))
            .combine_latest(self._price_stream, u(
                lambda balance, change, price: r(balance, price)
            ))
            .distinct_until_changed(u(
                lambda balance, price: balance
            ))
            .subscribe(u(
                lambda balance, price: self._create_buy_order(balance, price, self.REASON_BALANCE_CHANGED)
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
