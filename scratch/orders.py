def order_total(items):
    """The order's total in pence"""
    total = 0
    for item in items:
        total += item.price_pence * item.quantity
    return total


def is_free_shipping(total_pence):
    return total_pence > 5000
