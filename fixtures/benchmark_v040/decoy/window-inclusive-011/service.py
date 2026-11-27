"""Public integration surface for the window subsystem."""
from intervals import inside_window

def accept_timestamp(start, stop, sample):
    return inside_window(start, stop, sample)
