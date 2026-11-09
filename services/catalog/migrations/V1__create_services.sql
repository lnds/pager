-- Catálogo de servicios en producción. catalog es el dueño de esta base.
CREATE TABLE services (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    team        TEXT NOT NULL,
    slo_target  NUMERIC NOT NULL DEFAULT 99.9,
    sli_type    TEXT NOT NULL DEFAULT 'availability',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
