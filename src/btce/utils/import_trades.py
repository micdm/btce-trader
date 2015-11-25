from datetime import datetime
import json
import sys

from sqlalchemy import func

from common import get_logger, get_engine, get_session
from models import Trade


logger = get_logger(__name__)


_TYPE_BID = 0
_TYPE_ASK = 1


def _import_trades(history):
    engine = get_engine()
    session = get_session(engine)
    last_id = _get_last_stored_id(session)
    logger.debug('Last stored trade ID is %s', last_id)
    count = 0
    for trade in _get_trades(history, last_id):
        session.merge(trade)
        if count % 1000:
            session.commit()
        count += 1
    session.commit()
    logger.debug('Added %s trades', count)


def _get_last_stored_id(session):
    return session.query(func.max(Trade.id)).one()[0]


def _get_trades(history, last_id):
    for trades in history:
        for trade in trades:
            if last_id is None or trade['tid'] > last_id:
                yield Trade(id=trade['tid'], create_date=datetime.utcfromtimestamp(trade['timestamp']),
                            type=(_TYPE_BID if trade['type'] == 'bid' else _TYPE_ASK), amount=trade['amount'],
                            price=trade['price'])


def _main():
    with open(sys.argv[1]) as history:
        _import_trades(_get_deserialized_trades(history))


def _get_deserialized_trades(history):
    for item in history:
        try:
            yield json.loads(item)['btc_usd']
        except ValueError:
            logger.debug('Cannot deserialize "%s"', item)


if __name__ == '__main__':
    _main()
