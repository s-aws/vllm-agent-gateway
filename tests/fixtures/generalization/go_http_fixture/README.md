# Go HTTP Fixture

This fixture is a small Go HTTP service used to validate non-Python and non-Node repository generalization.

## Key Paths

- `cmd/server/main.go` starts the service and registers routes.
- `internal/orders/handler.go` owns order route handlers.
- `internal/orders/repository.go` owns in-memory persistence.
- `internal/config/config.go` reads configuration from environment variables.
- `internal/orders/handler_test.go` covers the order status route.

## Runtime

The order status timeout is controlled by `ORDER_STATUS_TIMEOUT_MS`.

Run tests with:

```bash
go test ./...
```
