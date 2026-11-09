package main

import (
	"log/slog"
	"net/http"
	"os"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))

	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	srv := NewServer(NewStore(), logger)
	logger.Info("notifications_listening", "port", port, "api_key", apiKey())
	if err := http.ListenAndServe(":"+port, srv); err != nil {
		logger.Error("server_stopped", "error", err)
		os.Exit(1)
	}
}
