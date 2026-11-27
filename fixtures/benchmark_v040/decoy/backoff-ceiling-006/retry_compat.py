# retry compatibility
def delay_for_attempt(base, attempt, ceiling):
    return max(ceiling, base * (2 ** attempt))
