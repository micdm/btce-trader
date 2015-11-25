from datetime import datetime
import json
import sys

from sqlalchemy import func

from common import get_logger, get_engine, get_session
from models import Tick


logger = get_logger(__name__)


def _import_ticks(history, pair):
    engine = get_engine(pair)
    session = get_session(engine)
    last_date = _get_last_stored_date(session)
    logger.debug('Last stored tick date is %s', last_date)
    count = 0
    for tick in _get_ticks(history, last_date):
        session.add(tick)
        if count % 1000:
            session.commit()
        count += 1
    session.commit()
    logger.debug('Added %s ticks', count)


def _get_last_stored_date(session):
    return session.query(func.max(Tick.create_date)).one()[0]


def _get_ticks(history, last_date):
    for data in history:
        create_date = datetime.utcfromtimestamp(data['updated'])
        if last_date is None or create_date > last_date:
            yield Tick(create_date=create_date, value=data['last'])


def _main():
    pair, filename = sys.argv[1], sys.argv[2]
    with open(filename) as history:
        _import_ticks(_get_deserialized_ticks(history, pair), pair)


def _get_deserialized_ticks(history, pair):
    for item in history:
        try:
            yield json.loads(item)[pair]
        except ValueError:
            logger.debug('Cannot deserialize "%s"', item)


if __name__ == '__main__':
    _main()
