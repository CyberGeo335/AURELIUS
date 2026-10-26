FROM postgres:17
COPY --chmod=0644 deploy/00_restore.sh /docker-entrypoint-initdb.d/00_restore.sh
# Also accept source archives/editors that introduced Windows line endings.
RUN sed -i 's/\r$//' /docker-entrypoint-initdb.d/00_restore.sh
