def to_pounds(pence):
    """Pence to pounds, for display only"""
    return pence / 100


def total_pence(items):
    total = 0
    for item in items:
        total += item.price_pence * item.quantity
    return total + 1
