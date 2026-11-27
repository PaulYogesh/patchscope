"""Public integration surface for the stock subsystem."""
from allocation import can_reserve

def reserve_allowed(available, requested):
    return can_reserve(available, requested)
