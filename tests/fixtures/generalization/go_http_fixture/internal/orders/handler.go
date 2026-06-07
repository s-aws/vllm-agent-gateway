package orders

import (
	"encoding/json"
	"net/http"

	"example.com/order-service/internal/config"
)

type createOrderRequest struct {
	OrderID string `json:"order_id"`
	Status  string `json:"status"`
}

type orderStatusResponse struct {
	OrderID   string `json:"order_id"`
	Status    string `json:"status"`
	TimeoutMS int    `json:"timeout_ms"`
}

func RegisterOrderRoutes(mux *http.ServeMux, repository Repository, settings config.Settings) {
	mux.HandleFunc("POST /orders", HandleCreateOrder(repository))
	mux.HandleFunc("GET /orders/status", HandleOrderStatus(repository, settings))
}

func HandleCreateOrder(repository Repository) http.HandlerFunc {
	return func(response http.ResponseWriter, request *http.Request) {
		var payload createOrderRequest
		if err := json.NewDecoder(request.Body).Decode(&payload); err != nil {
			http.Error(response, "invalid order payload", http.StatusBadRequest)
			return
		}
		if payload.OrderID == "" {
			http.Error(response, "order_id is required", http.StatusBadRequest)
			return
		}
		if payload.Status == "" {
			payload.Status = "pending"
		}
		repository.SaveOrder(Order{ID: payload.OrderID, Status: payload.Status})
		response.WriteHeader(http.StatusCreated)
	}
}

func HandleOrderStatus(repository Repository, settings config.Settings) http.HandlerFunc {
	return func(response http.ResponseWriter, request *http.Request) {
		orderID := request.URL.Query().Get("order_id")
		if orderID == "" {
			http.Error(response, "order_id is required", http.StatusBadRequest)
			return
		}
		order, found := repository.FindOrder(orderID)
		if !found {
			http.Error(response, "order not found", http.StatusNotFound)
			return
		}
		body := orderStatusResponse{
			OrderID:   order.ID,
			Status:    order.Status,
			TimeoutMS: settings.OrderStatusTimeoutMS,
		}
		response.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(response).Encode(body)
	}
}
