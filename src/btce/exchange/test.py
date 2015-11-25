from decimal import Decimal

from btce import config
from btce.common import SellOrder, BuyOrder, normalize_value, SECOND_CURRENCY_PLACES, get_engine, get_session, \
    get_logger, FirstCurrencyBalance, SecondCurrencyBalance
from btce.exchange.base import Exchange
from btce.models import Tick


logger = get_logger(__name__)


class TestExchange(Exchange):

    orders = []
    buy_orders = 0
    sell_orders = 0
    first_currency_balance = None
    second_currency_balance = None

    def init(self):
        (self._balance_stream
            .filter(lambda balance: isinstance(balance, FirstCurrencyBalance))
            .subscribe(lambda balance: setattr(self, 'first_currency_balance', balance.amount)))
        (self._balance_stream
            .filter(lambda balance: isinstance(balance, SecondCurrencyBalance))
            .subscribe(lambda balance: setattr(self, 'second_currency_balance', balance.amount)))
        (self._order_stream
            .filter(lambda order: isinstance(order, SellOrder))
            .subscribe(self._on_create_sell_order))
        (self._order_stream
            .filter(lambda order: isinstance(order, BuyOrder))
            .subscribe(self._on_create_buy_order))
        self._run()

    def _on_create_sell_order(self, order):
        def _close_order(price):
            logger.debug('Closing sell order %s', order)
            change = normalize_value(order.amount * order.price, SECOND_CURRENCY_PLACES)
            self._balance_stream.on_next(SecondCurrencyBalance(self.second_currency_balance +
                                                               change - change * config.EXCHANGE_MARGIN))
            subscription.dispose()
            self.orders.remove(order)
            self.sell_orders += 1
        logger.debug('Creating sell order %s', order)
        self._balance_stream.on_next(FirstCurrencyBalance(self.first_currency_balance - order.amount))
        subscription = (self._price_stream
            .filter(lambda price: price >= order.price)
            .subscribe(_close_order))
        self.orders.append(order)

    def _on_create_buy_order(self, order):
        def _close_order(price):
            logger.debug('Closing buy order %s', order)
            change = order.amount
            self._balance_stream.on_next(FirstCurrencyBalance(self.first_currency_balance +
                                                              change - change * config.EXCHANGE_MARGIN))
            subscription.dispose()
            self.orders.remove(order)
            self.buy_orders += 1
        logger.debug('Creating buy order %s', order)
        self._balance_stream.on_next(SecondCurrencyBalance(self.second_currency_balance -
                                                           normalize_value(order.amount * order.price,
                                                                           SECOND_CURRENCY_PLACES)))
        subscription = (self._price_stream
            .filter(lambda price: price <= order.price)
            .subscribe(_close_order))
        self.orders.append(order)

    def _run(self):
        self._balance_stream.on_next(FirstCurrencyBalance(Decimal(0)))
        self._balance_stream.on_next(SecondCurrencyBalance(Decimal(100)))
        engine = get_engine('%s_%s' % (config.FIRST_CURRENCY, config.SECOND_CURRENCY))
        session = get_session(engine)
        count = session.query(Tick).count()
        logger.debug('Records: %s', count)
        for i in range(0, count, 5000):
            for tick in session.query(Tick).order_by('create_date').offset(i).limit(5000):
                self._time_stream.on_next(tick.create_date)
                self._price_stream.on_next(tick.value)
        self._balance_stream.on_next(FirstCurrencyBalance(Decimal(0)))
        self._balance_stream.on_next(SecondCurrencyBalance(Decimal(0)))
