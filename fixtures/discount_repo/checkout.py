def final_price(price, discount_percent):
    """Apply percentage discount and return a nonnegative price."""
    if not 0 <= discount_percent <= 100:
        raise ValueError("Invalid discount")
    return max(0, price * (1 + discount_percent / 100))
