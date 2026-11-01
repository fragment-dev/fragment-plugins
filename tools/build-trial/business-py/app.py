"""A small online shop. Orders, customers and suppliers live in dicts for now."""

CUSTOMERS = {"cust-1": {"name": "Rivera Cafe"}, "cust-2": {"name": "Okafor Studio"}}
SUPPLIERS = {"sup-1": {"name": "Hill Roasters", "terms_days": 30}, "sup-2": {"name": "Box & Bag Co", "terms_days": 15}}
ORDERS = {}


def place_order(order_id: str, customer_id: str, items: list[dict]) -> dict:
    ORDERS[order_id] = {"customer": customer_id, "items": items}
    return {"ok": True}
