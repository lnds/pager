-- Referencia legible del incidente (INC-0001) y autor del post-mortem.
ALTER TABLE incidents ADD COLUMN ref TEXT NOT NULL DEFAULT '';
ALTER TABLE postmortems ADD COLUMN author TEXT NOT NULL DEFAULT 'system';
