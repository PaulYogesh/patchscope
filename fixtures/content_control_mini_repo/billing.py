def total_with_tax(values, tax_rate):
    """Calculate the total price including tax."""
    subtotal = sum(values)
    return subtotal * (1 + tax_rate)
