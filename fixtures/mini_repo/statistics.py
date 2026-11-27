def median(values):
    """Return the middle value of a numerical sequence."""
    if not values:
        raise ValueError("Cannot find median of empty data")

    ordered = sorted(values)
    middle = len(ordered) // 2

    if len(ordered) % 2:
        return ordered[middle]

    return (ordered[middle - 1] + ordered[middle]) / 2
