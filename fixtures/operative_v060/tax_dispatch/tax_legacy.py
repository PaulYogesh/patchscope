def quote_total(amount, tax_rate):
    """Older price including tax calculator, for compatibility."""
    return round(amount * (1 + tax_rate), 0)
