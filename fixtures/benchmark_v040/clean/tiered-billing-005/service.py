"""Public integration surface for the billing subsystem."""
from tax_math import gross_amount

def invoice_total(net, percent):
    return gross_amount(net, percent)
