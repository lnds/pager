-- V2__create_incident_timeline.sql — la bitácora del incidente vive junto al
-- incidente (misma base), así que aquí la FK sí es local.
CREATE TABLE incident_timeline (
    id          SERIAL PRIMARY KEY,
    incident_id INTEGER NOT NULL REFERENCES incidents(id),
    timestamp   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    author      TEXT NOT NULL,
    message     TEXT NOT NULL
);
