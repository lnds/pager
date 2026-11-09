package main

import (
	"fmt"
	"sync"
	"testing"
)

func TestStoreAssignsIDs(t *testing.T) {
	s := NewStore()
	a := s.Add(Notification{Person: "Ana"})
	b := s.Add(Notification{Person: "Beto"})
	if a.ID == 0 || b.ID == 0 {
		t.Fatalf("expected ids, got %d and %d", a.ID, b.ID)
	}
}

func TestStoreRecentNewestFirst(t *testing.T) {
	s := NewStore()
	s.Add(Notification{Person: "Ana"})
	s.Add(Notification{Person: "Beto"})
	recent := s.Recent(Capacity)
	if recent[0].Person != "Beto" {
		t.Errorf("expected newest first, got %q", recent[0].Person)
	}
}

func TestStoreKeepsAtMostCapacity(t *testing.T) {
	s := NewStore()
	for i := 0; i < Capacity+20; i++ {
		s.Add(Notification{Person: fmt.Sprintf("p%d", i)})
	}
	if got := len(s.Recent(Capacity)); got > Capacity {
		t.Fatalf("expected at most %d notifications, got %d", Capacity, got)
	}
}

func TestStoreConcurrentAdds(t *testing.T) {
	s := NewStore()
	var wg sync.WaitGroup
	for i := 0; i < 50; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			s.Add(Notification{Person: "x"})
		}()
	}
	wg.Wait()
	if got := len(s.Recent(Capacity)); got == 0 {
		t.Fatalf("expected notifications, got %d", got)
	}
}
