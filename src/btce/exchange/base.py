class Exchange:

    def __init__(self, time_stream, price_stream, balance_stream, order_stream):
        self._time_stream = time_stream
        self._price_stream = price_stream
        self._balance_stream = balance_stream
        self._order_stream = order_stream

    def init(self):
        raise NotImplementedError()
