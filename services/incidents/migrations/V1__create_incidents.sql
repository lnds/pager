-- V1__create_incidents.sql — incidents es dueño de esta base.
-- service_id NO es una FK: el servicio referenciado vive en OTRA base
-- (catalog). Guardamos service_name desnormalizado para no tener que
-- preguntarle al catálogo cada vez que listamos incidentes.
CREATE TABLE incidents (
    id           SERIAL PRIMARY KEY,
    service_id   INTEGER NOT NULL,
    service_name TEXT NOT NULL,
    title        TEXT NOT NULL,
    severity     INTEGER NOT NULL CHECK (severity BETWEEN 1 AND 4),
    status       TEXT NOT NULL DEFAULT 'open',
    started_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at  TIMESTAMPTZ,
    created_by   TEXT NOT NULL DEFAULT 'system'
);
