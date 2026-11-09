-- Turnos de guardia. La FK a services es local: ambas tablas viven en esta base.
CREATE TABLE shifts (
    id          SERIAL PRIMARY KEY,
    service_id  INTEGER NOT NULL REFERENCES services(id),
    person      TEXT NOT NULL,
    email       TEXT NOT NULL,
    start_date  DATE NOT NULL,
    end_date    DATE NOT NULL
);
