from decimal import Decimal
import logging
import logging.config

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from btce import config


FIRST_CURRENCY_PLACES = 6
SECOND_CURRENCY_PLACES = 3


def get_logger(name):
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '%(asctime)s [%(levelname)s] %(message)s'
            },
        },
        'handlers': {
            'null': {
                'level': 'DEBUG',
                'class': 'logging.NullHandler',
            },
            'console': {
                'level': 'DEBUG',
                'class': 'logging.StreamHandler',
                'formatter': 'verbose'
            },
        },
        'loggers': {
            '': {
                'handlers': ['console'],
                'level': 'DEBUG',
            },
            'sqlalchemy': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
        },
    })
    return logging.getLogger(name)


def get_engine(db_name):
    return create_engine('postgresql+psycopg2://%s:%s@%s:%s/%s' % (config.DB_USER, config.DB_PASSWORD, config.DB_HOST,
                                                                   config.DB_PORT, db_name))


def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()


def normalize_value(value, precision):
    return value.quantize(Decimal('10') ** -precision)


class Balance:

    def __init__(self, amount):
        self.amount = amount

    def __str__(self):
        return str(self.amount)


class FirstCurrencyBalance(Balance):
    pass


class SecondCurrencyBalance(Balance):
    pass


class Order:

    def __init__(self, amount, price):
        self.amount = amount
        self.price = price

    def __repr__(self):
        return str(self)


class BuyOrder(Order):

    def __str__(self):
        return '%s (buy %s for %s)' % (id(self), self.amount, self.price)


class SellOrder(Order):

    def __str__(self):
        return '%s (sell %s for %s)' % (id(self), self.amount, self.price)
