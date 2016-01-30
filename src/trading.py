from rx.subjects import Subject

from btce.common import get_logger
from btce.exchange import RealExchange
from btce.trader import Trader


logger = get_logger(__name__)


def _main():
    event_stream = Subject()
    command_stream = Subject()
    trader = Trader(event_stream, command_stream)
    trader.init()
    exchange = RealExchange(event_stream, command_stream)
    exchange.init()


if __name__ == '__main__':
    _main()
