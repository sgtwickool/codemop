from payments.ledger import InsufficientFunds, transfer


def pay_invoice(invoice, customer, shop):
    """Charge the customer for an invoice and mark it paid"""
    try:
        transfer(invoice.total, customer.account, shop.account)
    except InsufficientFunds:
        invoice.status = "declined"
        return False
    invoice.status = "paid"
    return True
