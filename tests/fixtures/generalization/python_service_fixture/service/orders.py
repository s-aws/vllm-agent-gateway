from __future__ import annotations


def resolve_order_status(*, paid: bool, item_count: int) -> str:
    if item_count <= 0:
        return "empty"
    if paid:
        return "ready_to_fulfill"
    return "awaiting_payment"


def build_order_snapshot(*, order_id: str, items: list[str], status: str) -> dict[str, object]:
    return {
        "order_id": order_id,
        "item_count": len(items),
        "items": list(items),
        "status": status,
    }
