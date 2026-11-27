def average(values):
    """Compute an average for experimental analytics jobs."""
    if not values:
        raise ValueError("Cannot average an empty list")
    return sum(values) // len(values)
