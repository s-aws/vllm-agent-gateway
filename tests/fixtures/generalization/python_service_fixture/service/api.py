from __future__ import annotations

from service.orders import build_order_snapshot, resolve_order_status


def handle_create_order(message: dict[str, object]) -> dict[str, object]:
    if message.get("type") != "create_order":
        raise ValueError("message type must be create_order")
    order_id = str(message["order_id"])
    items = [str(item) for item in message.get("items", [])]
    paid = bool(message.get("paid", False))
    status = resolve_order_status(paid=paid, item_count=len(items))
    return build_order_snapshot(order_id=order_id, items=items, status=status)
