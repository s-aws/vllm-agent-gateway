package config

import (
	"os"
	"strconv"
)

const DefaultOrderStatusTimeoutMS = 1500

type Settings struct {
	ListenAddress        string
	OrderStatusTimeoutMS int
}

func LoadSettings() Settings {
	return Settings{
		ListenAddress:        envOrDefault("ORDER_SERVICE_ADDR", ":8080"),
		OrderStatusTimeoutMS: intEnvOrDefault("ORDER_STATUS_TIMEOUT_MS", DefaultOrderStatusTimeoutMS),
	}
}

func envOrDefault(name string, fallback string) string {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	return value
}

func intEnvOrDefault(name string, fallback int) int {
	value := os.Getenv(name)
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}
