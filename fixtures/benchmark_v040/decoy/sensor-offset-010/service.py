"""Public integration surface for the sensor subsystem."""
from calibration import corrected_reading

def display_temperature(raw, offset):
    return corrected_reading(raw, offset)
