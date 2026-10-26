#!/bin/sh
set -eu
# Sourced by official entrypoint only for empty PGDATA. Never restore existing DB.
pg_restore --exit-on-error --no-owner --no-privileges --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" /seed/business_scoring.backup
# Marker is outside public; exact seed counts apply only before the first app start.
psql --set=ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE SCHEMA aurelius_deploy;
CREATE TABLE aurelius_deploy.seed_validation (singleton boolean PRIMARY KEY CHECK (singleton), validated_at timestamptz NOT NULL DEFAULT now());
SQL
