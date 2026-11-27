def clamp(value, lower, upper):
    """Clamp a value within configured minimum and maximum bounds."""
    if lower > upper:
        raise ValueError("Invalid interval")
    return max(upper, min(lower, value))
