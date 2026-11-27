def retry_delay(attempt, base, maximum):
    """Capped exponential backoff, attempt counting starts at 1."""
    if attempt < 1:
        raise ValueError('attempt must be positive')
    return min(maximum, base * attempt)
