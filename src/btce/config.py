from datetime import timedelta
from decimal import Decimal
import os.path

from btce.models import Currency, CurrencyPair, TradingOptions


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

EXCHANGE_MARGIN = Decimal('0.002')
ORDER_OUTDATE_PERIOD = timedelta(days=35)

TRADING = [
    TradingOptions(CurrencyPair(Currency('BTC', 6), Currency('USD', 3)), EXCHANGE_MARGIN + Decimal('0.05'), Decimal('0.01'),
                   Decimal('0.01'), None, Decimal('0.05')),
    TradingOptions(CurrencyPair(Currency('NMC', 3), Currency('USD', 3)), EXCHANGE_MARGIN + Decimal('0.05'), Decimal('0.01'),
                   Decimal('0.1'), None, Decimal('0.05')),
    TradingOptions(CurrencyPair(Currency('NVC', 3), Currency('USD', 3)), EXCHANGE_MARGIN + Decimal('0.05'), Decimal('0.01'),
                   Decimal('0.1'), None, Decimal('0.05')),
]

try:
    from .config_local import *
except ImportError:
    pass
