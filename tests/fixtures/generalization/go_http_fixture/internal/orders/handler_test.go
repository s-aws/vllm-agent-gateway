package orders

import (
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"example.com/order-service/internal/config"
)

func TestHandleOrderStatusReturnsTimeoutFromSettings(t *testing.T) {
	repository := NewMemoryRepository()
	repository.SaveOrder(Order{ID: "ord-123", Status: "accepted"})

	request := httptest.NewRequest(http.MethodGet, "/orders/status?order_id=ord-123", nil)
	response := httptest.NewRecorder()

	HandleOrderStatus(repository, config.Settings{OrderStatusTimeoutMS: 2500})(response, request)

	if response.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d", response.Code)
	}
	if !strings.Contains(response.Body.String(), `"timeout_ms":2500`) {
		t.Fatalf("expected timeout in response body, got %s", response.Body.String())
	}
}
