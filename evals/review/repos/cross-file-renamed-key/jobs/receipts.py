from orders.serialize import order_to_dict


def send_receipt(order, customers, mailer):
    """Email the customer a receipt for their order"""
    data = order_to_dict(order)
    customer = customers.get(data["customer_id"])
    mailer.send(customer.email, "Your receipt", f"Order {data['id']}: {data['total'] / 100:.2f}")
