from decimal import Decimal
import logging
import logging.config

from rx.concurrency import IOLoopScheduler

MAIN_THREAD = IOLoopScheduler()


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
            'tornado': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
            'Rx': {
                'handlers': ['console'],
                'level': 'WARNING',
                'propagate': False,
            },
        },
    })
    return logging.getLogger(name)


def normalize_value(value, precision):
    return value.quantize(Decimal('10') ** -precision)
