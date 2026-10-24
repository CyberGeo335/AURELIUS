#!/bin/sh
set -eu
# Official postgres entrypoint runs this only for a new/empty PGDATA volume.
pg_restore --exit-on-error --no-owner --no-privileges --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" /seed/business_scoring.backup
