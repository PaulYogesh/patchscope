import importlib
from config import ACTIVE_PRICER

def quote_total(amount, tax_rate):
    engine = importlib.import_module(ACTIVE_PRICER)
    return engine.quote_total(amount, tax_rate)
