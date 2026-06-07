package main

import (
	"log"
	"net/http"

	"example.com/order-service/internal/config"
	"example.com/order-service/internal/orders"
)

func main() {
	settings := config.LoadSettings()
	repository := orders.NewMemoryRepository()
	mux := http.NewServeMux()

	orders.RegisterOrderRoutes(mux, repository, settings)

	log.Printf("starting order service on %s", settings.ListenAddress)
	if err := http.ListenAndServe(settings.ListenAddress, mux); err != nil {
		log.Fatal(err)
	}
}
