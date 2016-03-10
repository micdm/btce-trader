from tornado.ioloop import IOLoop

from btce import config
from btce.common import get_logger
from btce.trading import Trading

logger = get_logger(__name__)


if __name__ == '__main__':
    for options in config.TRADING:
        logger.debug('Starting trade %s/%s', options.first_currency.name, options.second_currency.name)
        trading = Trading(options)
        trading.init()
    IOLoop.instance().start()
