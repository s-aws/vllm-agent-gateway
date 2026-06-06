from __future__ import annotations

import pytest

from service.api import handle_create_order
from service.orders import resolve_order_status


def test_resolve_order_status_ready_to_fulfill() -> None:
    assert resolve_order_status(paid=True, item_count=2) == "ready_to_fulfill"


def test_resolve_order_status_empty_order() -> None:
    assert resolve_order_status(paid=True, item_count=0) == "empty"


def test_handle_create_order_rejects_wrong_message_type() -> None:
    with pytest.raises(ValueError, match="message type must be create_order"):
        handle_create_order({"type": "cancel_order", "order_id": "ord-1"})
