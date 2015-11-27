from decimal import Decimal
import os.path

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

DB_HOST = 'localhost'
DB_PORT = 5432
DB_USER = 'postgres'
DB_PASSWORD = ''

API_KEY = None
API_SECRET = None

FIRST_CURRENCY = 'btc'
SECOND_CURRENCY = 'usd'

EXCHANGE_MARGIN = Decimal('0.002')
TRADER_MARGIN = Decimal('0.05')
MARGIN = EXCHANGE_MARGIN + TRADER_MARGIN
MIN_AMOUNT = Decimal('0.01')
DEAL_AMOUNT = MIN_AMOUNT

try:
    from .config_local import *
except ImportError:
    pass
