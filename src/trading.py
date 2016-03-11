from rx.subjects import Subject

from btce import config
from btce.common import get_logger
from btce.exchange import ExchangeConnector
from btce.trader import Trader


logger = get_logger(__name__)


if __name__ == '__main__':
    event_stream = Subject()
    command_stream = Subject()
    connector = ExchangeConnector(event_stream, command_stream)
    connector.init()
    traders = []
    for options in config.TRADING:
        trader = Trader(options, event_stream, command_stream)
        trader.init()
        traders.append(trader)
    try:
        connector.run()
    except:
        for trader in traders:
            trader.deinit()
        connector.deinit()
