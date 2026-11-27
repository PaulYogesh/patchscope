def display_reference(prefix, serial_number):
    """Build a stable, human-readable reference string for receipts and logs in a back-office UI."""
    if not prefix:
        prefix = "REC"
    number = str(serial_number).strip()
    return f"{prefix}-{number}"
