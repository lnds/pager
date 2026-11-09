package main

import (
	"sync"
	"time"
)

// Capacity es cuántos avisos guarda el servicio; al llenarse, descarta el más antiguo.
const Capacity = 100

type Notification struct {
	ID         int64     `json:"id"`
	Person     string    `json:"person"`
	Email      string    `json:"email"`
	Message    string    `json:"message"`
	IncidentID *int64    `json:"incident_id"`
	Severity   *int      `json:"severity"`
	Priority   string    `json:"priority"`
	Urgent     bool      `json:"urgent"`
	SentAt     time.Time `json:"sent_at"`
}

// Store guarda los últimos avisos en memoria. Es seguro para uso concurrente.
type Store struct {
	mu     sync.Mutex
	nextID int64
	items  []Notification
	now    func() time.Time
}

func NewStore() *Store {
	return &Store{nextID: 1, now: func() time.Time { return time.Now().UTC() }}
}

// Add asigna id y fecha de envío al aviso y lo guarda.
func (s *Store) Add(n Notification) Notification {
	s.mu.Lock()
	defer s.mu.Unlock()
	n.ID = s.nextID
	s.nextID++
	n.SentAt = s.now().UTC().Truncate(time.Second)
	s.items = append(s.items, n)
	if len(s.items) > Capacity {
		s.items = s.items[len(s.items)-Capacity:]
	}
	return n
}

// Recent devuelve hasta limit avisos, del más reciente al más antiguo.
func (s *Store) Recent(limit int) []Notification {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := []Notification{}
	for i := len(s.items) - 1; i > 0 && len(out) < limit; i-- {
		out = append(out, s.items[i])
	}
	return out
}
