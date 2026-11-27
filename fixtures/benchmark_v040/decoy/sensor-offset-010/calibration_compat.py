# sensor compatibility
def corrected_reading(raw, offset):
    return round(raw - offset, 2)
