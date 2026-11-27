
def average(values):
    if not values:
        raise ValueError("Cannot average an empty list")

    return sum(values) // len(values)
