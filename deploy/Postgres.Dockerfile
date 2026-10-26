FROM postgres:17
COPY --chmod=0644 deploy/00_restore.sh /docker-entrypoint-initdb.d/00_restore.sh
