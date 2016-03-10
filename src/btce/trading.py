from rx.subjects import Subject

from btce.exchange import RealExchange
from btce.trader import Trader


class Trading:

    def __init__(self, options):
        event_stream = Subject()
        command_stream = Subject()
        self._trader = Trader(options, event_stream, command_stream)
        self._exchange = RealExchange(options, event_stream, command_stream)

    def init(self):
        self._trader.init()
        self._exchange.init()
