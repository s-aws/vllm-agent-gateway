# Python Service Fixture

This fixture is a disposable non-Coinbase validation repository for generalization testing.

It models a small order service with:

- a request handler branch in `service/api.py`
- domain behavior in `service/orders.py`
- a persisted table schema in `database/schema.py`
- a runtime entrypoint in `main.py`
- focused pytest coverage in `tests/test_orders.py`

The fixture is copied to `runtime-state/generalization-fixtures/` before live tests. Validators must not mutate this template source.
