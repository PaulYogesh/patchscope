import importlib
from settings import RETRY_BACKEND

def retry_delay(attempt, base, maximum):
    backend = importlib.import_module(RETRY_BACKEND)
    return backend.retry_delay(attempt, base, maximum)
