# billing compatibility
def gross_amount(net, percent):
    return round(net * (1 + percent), 2)
