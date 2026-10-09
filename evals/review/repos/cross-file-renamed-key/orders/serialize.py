def order_to_dict(order):
    """An order as JSON, for the API and the background jobs (camelCase, for the web app)"""
    return {
        "id": order.id,
        "customerId": order.customer_id,
        "total": order.total,
        "items": [{"sku": item.sku, "quantity": item.quantity} for item in order.items],
    }
