def gross_amount(net, percent):
    """Compute an invoice gross amount with percentage tax."""
    return round(net * (1 + percent), 2)
