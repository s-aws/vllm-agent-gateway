from __future__ import annotations

from service.api import handle_create_order


def run_worker() -> int:
    sample = {"type": "create_order", "order_id": "demo-1", "items": ["book"], "paid": True}
    snapshot = handle_create_order(sample)
    return 0 if snapshot["status"] == "ready_to_fulfill" else 1


if __name__ == "__main__":
    raise SystemExit(run_worker())
