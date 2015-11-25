from argparse import ArgumentParser

from rx.subjects import Subject

from btce.common import get_logger
from btce.exchange.test import TestExchange
from btce.exchange.real import RealExchange
from btce.trader import Trader


logger = get_logger(__name__)


def _get_options():
    parser = ArgumentParser(description='Start making money.')
    parser.add_argument('-m', '--mode', choices=('test', 'real'), help='set exchange mode (test by default)')
    return parser.parse_args()


def _main(options):
    time_stream = Subject()
    price_stream = Subject()
    balance_stream = Subject()
    order_stream = Subject()
    trader_class = _get_trader_class()
    trader = trader_class(time_stream, price_stream, balance_stream, order_stream)
    trader.init()
    exchange_class = _get_exchange_class(options)
    exchange = exchange_class(time_stream, price_stream, balance_stream, order_stream)
    exchange.init()


def _get_trader_class():
    return Trader


def _get_exchange_class(options):
    return RealExchange if options.mode == 'real' else TestExchange


if __name__ == '__main__':
    options = _get_options()
    _main(options)
