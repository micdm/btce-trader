from datetime import timedelta
from decimal import Decimal
import os.path


BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
SRC_DIR = os.path.join(BASE_DIR, 'src')
DATA_DIR = os.path.join(BASE_DIR, 'data')
TEST_DIR = os.path.join(SRC_DIR, 'tests')

DB_HOST = 'localhost'
DB_PORT = 5432
DB_USER = 'postgres'
DB_PASSWORD = ''

EXCHANGE_SITE = 'https://btc-e.nz'

API_KEY = None
API_SECRET = None

FIRST_CURRENCY = 'btc'
SECOND_CURRENCY = 'usd'

EXCHANGE_MARGIN = Decimal('0.002')
TRADER_MARGIN = Decimal('0.05')
MARGIN = EXCHANGE_MARGIN + TRADER_MARGIN
MARGIN_JITTER = Decimal('0.01')
MIN_AMOUNT = Decimal('0.01')
DEAL_AMOUNT = MIN_AMOUNT
PRICE_JUMP_VALUE = Decimal('0.05')
ORDER_OUTDATE_PERIOD = timedelta(days=30)


try:
    from .config_local import *
except ImportError:
    pass
