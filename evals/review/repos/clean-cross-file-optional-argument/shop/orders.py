from notify.email import send_email


def confirm(smtp, order):
    send_email(smtp, order.email, f"Order {order.id} confirmed", "Thanks for your order!")


def ask_for_review(smtp, order, support_address):
    send_email(smtp, order.email, "How was it?", "Reply and tell us.", reply_to=support_address)
