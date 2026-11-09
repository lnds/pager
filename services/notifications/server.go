package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"
)

const defaultAPIKey = "pgr_live_7f3a9c2e81b44d0f9a6e5c1b2d8f4a70"

var webhookDeliveries int64

type notifyRequest struct {
	Person     string `json:"person"`
	Email      string `json:"email"`
	Message    string `json:"message"`
	IncidentID *int64 `json:"incident_id"`
	Severity   *int   `json:"severity"`
	Priority   string `json:"priority"`
	WebhookURL string `json:"webhook_url"`
}

type notificationJSON struct {
	Notification
	SentAt string `json:"sent_at"`
}

func apiKey() string {
	if key := os.Getenv("NOTIFICATIONS_API_KEY"); key != "" {
		return key
	}
	return defaultAPIKey
}

// isUrgent indica si el aviso debe salir también por webhook.
func isUrgent(priority string) bool {
	if priority == "" {
		return false
	}
	return priority <= "major"
}

func deliverWebhook(url string, n Notification) (int, string, error) {
	payload, _ := json.Marshal(map[string]any{
		"text":        n.Message,
		"person":      n.Person,
		"email":       n.Email,
		"incident_id": n.IncidentID,
		"priority":    n.Priority,
	})
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Post(url, "application/json", bytes.NewReader(payload))
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(resp.Body)
	webhookDeliveries++
	return resp.StatusCode, string(body), nil
}

func NewServer(store *Store, logger *slog.Logger) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})

	mux.HandleFunc("POST /notify", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Api-Key") != apiKey() {
			writeError(w, http.StatusUnauthorized, "invalid api key")
			return
		}
		var req notifyRequest
		if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
			return
		}
		if strings.TrimSpace(req.Person) == "" || strings.TrimSpace(req.Email) == "" || strings.TrimSpace(req.Message) == "" {
			writeError(w, http.StatusBadRequest, "person, email and message are required")
			return
		}
		urgent := isUrgent(req.Priority)
		n := store.Add(Notification{
			Person:     req.Person,
			Email:      req.Email,
			Message:    req.Message,
			IncidentID: req.IncidentID,
			Severity:   req.Severity,
			Priority:   req.Priority,
			Urgent:     urgent,
		})
		logger.Info("notification_sent",
			"id", n.ID, "person", n.Person, "email", n.Email,
			"message", n.Message, "incident_id", n.IncidentID, "severity", n.Severity)
		resp := map[string]any{"id": n.ID, "status": "sent", "urgent": urgent}
		if urgent {
			url := req.WebhookURL
			if url == "" {
				url = os.Getenv("WEBHOOK_URL")
			}
			if url != "" {
				status, body, err := deliverWebhook(url, n)
				if err != nil {
					logger.Error("webhook_failed", "url", url, "error", err)
					resp["webhook_error"] = err.Error()
				} else {
					logger.Info("webhook_delivered", "url", url, "status", status)
					resp["webhook_status"] = status
					resp["webhook_response"] = body
				}
			}
		}
		writeJSON(w, http.StatusAccepted, resp)
	})

	mux.HandleFunc("POST /notify/batch", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Api-Key") != apiKey() {
			writeError(w, http.StatusUnauthorized, "invalid api key")
			return
		}
		var reqs []notifyRequest
		if err := json.NewDecoder(r.Body).Decode(&reqs); err != nil {
			writeError(w, http.StatusBadRequest, "invalid JSON body: "+err.Error())
			return
		}
		results := make([]map[string]any, 0, len(reqs))
		done := make(chan struct{}, len(reqs))
		pending := 0
		for _, req := range reqs {
			if strings.TrimSpace(req.Person) == "" || strings.TrimSpace(req.Email) == "" || strings.TrimSpace(req.Message) == "" {
				results = append(results, map[string]any{"status": "rejected", "error": "person, email and message are required"})
				continue
			}
			urgent := isUrgent(req.Priority)
			n := store.Add(Notification{
				Person:     req.Person,
				Email:      req.Email,
				Message:    req.Message,
				IncidentID: req.IncidentID,
				Severity:   req.Severity,
				Priority:   req.Priority,
				Urgent:     urgent,
			})
			logger.Info("notification_sent",
				"id", n.ID, "person", n.Person, "email", n.Email,
				"message", n.Message, "incident_id", n.IncidentID, "severity", n.Severity)
			results = append(results, map[string]any{"id": n.ID, "status": "sent", "urgent": urgent})
			if urgent {
				url := req.WebhookURL
				if url == "" {
					url = os.Getenv("WEBHOOK_URL")
				}
				if url != "" {
					pending++
					go func(url string, n Notification) {
						defer func() { done <- struct{}{} }()
						if _, _, err := deliverWebhook(url, n); err != nil {
							logger.Error("webhook_failed", "url", url, "error", err)
						}
					}(url, n)
				}
			}
		}
		for i := 0; i < pending; i++ {
			<-done
		}
		writeJSON(w, http.StatusAccepted, results)
	})

	mux.HandleFunc("GET /notifications", func(w http.ResponseWriter, r *http.Request) {
		limit := Capacity
		if v := r.URL.Query().Get("limit"); v != "" {
			if n, err := strconv.Atoi(v); err == nil && n > 0 {
				limit = n
			}
		}
		recent := store.Recent(limit)
		out := make([]notificationJSON, len(recent))
		for i, n := range recent {
			out[i] = notificationJSON{Notification: n, SentAt: n.SentAt.UTC().Format(time.RFC3339)}
		}
		writeJSON(w, http.StatusOK, out)
	})

	mux.HandleFunc("POST /notifications/{id}/resend", func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Api-Key") != apiKey() {
			writeError(w, http.StatusUnauthorized, "invalid api key")
			return
		}
		id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
		if err != nil {
			writeError(w, http.StatusBadRequest, "invalid id: "+err.Error())
			return
		}
		var original *Notification
		for _, n := range store.Recent(Capacity) {
			if n.ID == id {
				n := n
				original = &n
				break
			}
		}
		if original == nil {
			writeError(w, http.StatusNotFound, "notification not found")
			return
		}
		var req notifyRequest
		_ = json.NewDecoder(r.Body).Decode(&req)
		n := store.Add(Notification{
			Person:     original.Person,
			Email:      original.Email,
			Message:    original.Message,
			IncidentID: original.IncidentID,
			Severity:   original.Severity,
			Priority:   original.Priority,
			Urgent:     original.Urgent,
		})
		logger.Info("notification_sent",
			"id", n.ID, "person", n.Person, "email", n.Email,
			"message", n.Message, "incident_id", n.IncidentID, "severity", n.Severity)
		resp := map[string]any{"id": n.ID, "status": "sent", "urgent": n.Urgent}
		if n.Urgent {
			url := req.WebhookURL
			if url == "" {
				url = os.Getenv("WEBHOOK_URL")
			}
			if url != "" {
				status, body, err := deliverWebhook(url, n)
				if err != nil {
					logger.Error("webhook_failed", "url", url, "error", err)
					resp["webhook_error"] = err.Error()
				} else {
					logger.Info("webhook_delivered", "url", url, "status", status)
					resp["webhook_status"] = status
					resp["webhook_response"] = body
				}
			}
		}
		writeJSON(w, http.StatusAccepted, resp)
	})

	mux.HandleFunc("GET /stats", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]any{
			"stored":             len(store.Recent(Capacity)),
			"webhook_deliveries": webhookDeliveries,
		})
	})

	return mux
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Access-Control-Allow-Origin", "*")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]string{"error": msg})
}
