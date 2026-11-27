def can_reserve(available, requested):
    """Return whether the requested quantity can be allocated."""
    return requested < available
