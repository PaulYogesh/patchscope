def retry_delay(attempt, base, maximum):
    """Capped exponential-style retry delay for a compatibility client."""
    if attempt < 1:
        raise ValueError('attempt must be positive')
    return min(maximum, base * attempt)
