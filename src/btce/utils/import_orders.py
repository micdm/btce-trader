from datetime import datetime
import json
import sys

from sqlalchemy import func

from common import get_logger, get_engine, get_session
from models import Order


logger = get_logger(__name__)


_TYPE_BID = 0
_TYPE_ASK = 1


def _import_orders(history):
    engine = get_engine()
    session = get_session(engine)
    last_date = _get_last_stored_date(session)
    logger.debug('Last stored actual date is %s', last_date)
    count = 0
    for order in _get_orders(history, last_date):
        session.merge(order)
        if count % 1000:
            session.commit()
        count += 1
    session.commit()
    logger.debug('Added %s orders', count)


def _get_last_stored_date(session):
    return session.query(func.max(Order.actual_date)).one()[0]


def _get_orders(history, last_date):
    for actual_date, orders in history:
        for order_type, orders in orders.items():
            for order in orders:
                if last_date is None or actual_date > last_date:
                    yield Order(actual_date=actual_date, type=(_TYPE_BID if order_type == 'bids' else _TYPE_ASK),
                                amount=order[1], price=order[0])


def _main():
    with open(sys.argv[1]) as history:
        _import_orders(_get_deserialized_orders(history))


def _get_deserialized_orders(history):
    actual_date = None
    for item in history:
        if actual_date is None:
            actual_date = datetime.strptime(item.strip(), '%a %b %d %H:%M:%S UTC %Y')
        else:
            try:
                yield actual_date, json.loads(item)['btc_usd']
            except ValueError:
                logger.debug('Cannot deserialize "%s"', item)
            actual_date = None


if __name__ == '__main__':
    _main()
