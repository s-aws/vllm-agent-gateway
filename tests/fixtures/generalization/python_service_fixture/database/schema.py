from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OrderRecord:
    id: str
    status: str
    item_count: int
    created_at: str


ORDERS_TABLE_SCHEMA = {
    "table": "orders",
    "fields": {
        "id": "text primary key",
        "status": "text not null",
        "item_count": "integer not null",
        "created_at": "timestamp not null",
    },
}

ORDERS_TABLE_SQL = """
CREATE TABLE orders (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    item_count INTEGER NOT NULL,
    created_at TIMESTAMP NOT NULL
);
"""
