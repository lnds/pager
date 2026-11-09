-- V3__create_postmortems.sql — el post-mortem también pertenece al incidente.
CREATE TABLE postmortems (
    id           SERIAL PRIMARY KEY,
    incident_id  INTEGER NOT NULL UNIQUE REFERENCES incidents(id),
    summary      TEXT NOT NULL,
    root_cause   TEXT NOT NULL,
    impact       TEXT NOT NULL,
    action_items TEXT NOT NULL,
    lessons      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
