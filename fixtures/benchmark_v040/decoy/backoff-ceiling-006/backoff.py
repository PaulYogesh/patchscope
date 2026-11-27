def delay_for_attempt(base, attempt, ceiling):
    """Compute capped exponential retry delays in seconds."""
    return max(ceiling, base * (2 ** attempt))
