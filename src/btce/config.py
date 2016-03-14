from datetime import timedelta
from decimal import Decimal
import os.path

from btce.models import CurrencyPair, TradingOptions, CURRENCY_BTC, CURRENCY_USD, CURRENCY_NMC, CURRENCY_NVC, \
    CURRENCY_LTC, CURRENCY_PPC

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
DEFAULT_OVERALL_MARGIN = EXCHANGE_MARGIN + Decimal('0.05')
DEFAULT_MARGIN_JITTER = Decimal('0.01')
DEFAULT_JUMPING_PRICE = Decimal('0.05')
ORDER_OUTDATE_PERIOD = timedelta(days=35)

def _get_default_trading_options(pair, min_amount):
    return TradingOptions(pair, DEFAULT_OVERALL_MARGIN, DEFAULT_MARGIN_JITTER, min_amount, min_amount,
                          DEFAULT_JUMPING_PRICE)

TRADING = [
    _get_default_trading_options(CurrencyPair(CURRENCY_BTC, CURRENCY_USD), Decimal('0.01')),
    _get_default_trading_options(CurrencyPair(CURRENCY_LTC, CURRENCY_USD), Decimal('0.1')),
    _get_default_trading_options(CurrencyPair(CURRENCY_NMC, CURRENCY_USD), Decimal('0.1')),
    _get_default_trading_options(CurrencyPair(CURRENCY_NVC, CURRENCY_USD), Decimal('0.1')),
    _get_default_trading_options(CurrencyPair(CURRENCY_PPC, CURRENCY_USD), Decimal('0.1')),
]

try:
    from .config_local import *
except ImportError:
    pass
