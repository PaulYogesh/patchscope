def inside_window(start, stop, sample):
    """Use the half-open [start, stop) sampling convention."""
    return start < sample < stop
