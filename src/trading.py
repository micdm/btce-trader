from rx.subjects import Subject

from btce import config
from btce.common import get_logger
from btce.exchange import RealExchange
from btce.trader import Trader


logger = get_logger(__name__)


if __name__ == '__main__':
    event_stream = Subject()
    command_stream = Subject()
    exchange = RealExchange(event_stream, command_stream)
    for options in config.TRADING:
        logger.debug('Starting %s trader', options.pair)
        trader = Trader(options, event_stream, command_stream)
        trader.init()
    exchange.init()
