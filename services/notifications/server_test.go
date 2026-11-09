package main

import (
	"encoding/json"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func newTestServer() http.Handler {
	return NewServer(NewStore(), slog.New(slog.NewJSONHandler(io.Discard, nil)))
}

func do(t *testing.T, h http.Handler, method, path, body string) *httptest.ResponseRecorder {
	t.Helper()
	req := httptest.NewRequest(method, path, strings.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Api-Key", defaultAPIKey)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	return rec
}

func TestHealth(t *testing.T) {
	rec := do(t, newTestServer(), "GET", "/health", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}

func TestNotifyAccepted(t *testing.T) {
	rec := do(t, newTestServer(), "POST", "/notify",
		`{"person":"Ana Soto","email":"ana@example.com","message":"[SEV2] Latencia alta","incident_id":7,"severity":2,"priority":"major"}`)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d: %s", rec.Code, rec.Body.String())
	}
}

func TestNotifyRequiresFields(t *testing.T) {
	rec := do(t, newTestServer(), "POST", "/notify", `{"email":"ana@example.com","message":"hola"}`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestNotifyRejectsInvalidJSON(t *testing.T) {
	rec := do(t, newTestServer(), "POST", "/notify", `{not json`)
	if rec.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", rec.Code)
	}
}

func TestNotifyWebhook(t *testing.T) {
	hook := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	}))
	defer hook.Close()
	rec := do(t, newTestServer(), "POST", "/notify",
		`{"person":"Ana","email":"ana@example.com","message":"caída","priority":"critical","webhook_url":"`+hook.URL+`"}`)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", rec.Code)
	}
}

func TestNotifyBatch(t *testing.T) {
	rec := do(t, newTestServer(), "POST", "/notify/batch",
		`[{"person":"Ana","email":"ana@example.com","message":"uno"},{"person":"","email":"x","message":"dos"}]`)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", rec.Code)
	}
}

func TestListNotifications(t *testing.T) {
	h := newTestServer()
	do(t, h, "POST", "/notify", `{"person":"Ana","email":"ana@example.com","message":"uno"}`)
	do(t, h, "POST", "/notify", `{"person":"Beto","email":"beto@example.com","message":"dos"}`)

	rec := do(t, h, "GET", "/notifications", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
	var got []map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &got); err != nil {
		t.Fatalf("invalid JSON: %v", err)
	}
	if len(got) == 0 {
		t.Fatalf("expected notifications")
	}
}

func TestListNotificationsWithLimit(t *testing.T) {
	h := newTestServer()
	do(t, h, "POST", "/notify", `{"person":"Ana","email":"ana@example.com","message":"uno"}`)
	rec := do(t, h, "GET", "/notifications?limit=1", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}

func TestStats(t *testing.T) {
	rec := do(t, newTestServer(), "GET", "/stats", "")
	if rec.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", rec.Code)
	}
}

func TestIsUrgent(t *testing.T) {
	if !isUrgent("critical") {
		t.Errorf("critical should be urgent")
	}
	if isUrgent("") {
		t.Errorf("empty priority should not be urgent")
	}
}

func TestMethodNotAllowed(t *testing.T) {
	rec := do(t, newTestServer(), "GET", "/notify", "")
	if rec.Code != http.StatusMethodNotAllowed {
		t.Fatalf("expected 405, got %d", rec.Code)
	}
}

func TestResend(t *testing.T) {
	h := newTestServer()
	do(t, h, "POST", "/notify", `{"person":"Ana","email":"ana@example.com","message":"uno"}`)
	do(t, h, "POST", "/notify", `{"person":"Beto","email":"beto@example.com","message":"dos"}`)
	rec := do(t, h, "POST", "/notifications/2/resend", `{}`)
	if rec.Code != http.StatusAccepted {
		t.Fatalf("expected 202, got %d", rec.Code)
	}
}
