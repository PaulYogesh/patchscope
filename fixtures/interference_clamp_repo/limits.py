def clamp(value, lower, upper):
    """Keep a number inside the inclusive lower/upper bounds."""
    if lower > upper:
        raise ValueError("Invalid interval")
    return max(upper, min(lower, value))
