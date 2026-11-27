def quote_total(amount, tax_rate):
    """Price including tax, rounded to two decimal places."""
    return round(amount * (1 + tax_rate), 0)
