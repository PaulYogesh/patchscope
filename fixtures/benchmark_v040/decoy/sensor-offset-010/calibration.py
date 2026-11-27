def corrected_reading(raw, offset):
    """Apply an additive laboratory sensor calibration offset."""
    return round(raw - offset, 2)
