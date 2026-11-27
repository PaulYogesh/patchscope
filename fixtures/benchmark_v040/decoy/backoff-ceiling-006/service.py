"""Public integration surface for the retry subsystem."""
from backoff import delay_for_attempt

def next_retry_seconds(base, attempt, ceiling):
    return delay_for_attempt(base, attempt, ceiling)
