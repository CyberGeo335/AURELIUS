#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then
    echo 'Создайте .env: cp .env.example .env; задайте POSTGRES_PASSWORD.' >&2
    exit 1
fi
unset OLLAMA_ENDPOINT
# Build once; probe runs inside Docker, so no host Python/curl/Ollama is required.
docker compose build app
set +e
docker compose run --rm --no-deps probe
probe_status=$?
set -e
case "$probe_status" in
    0) ;;
    2) export OLLAMA_ENDPOINT=http://ollama:11434
       docker compose --profile bundled up -d ollama ;;
    *) echo "Проверка Ollama завершилась ошибкой ($probe_status). См. вывод выше." >&2; exit "$probe_status" ;;
esac
docker compose up -d db init model-init
docker compose logs -f model-init
model_container=$(docker compose ps --all --quiet model-init)
model_state=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$model_container")
if [ "$model_state" != 'exited 0' ]; then
    echo "Модель не готова ($model_state). См. docker compose logs model-init." >&2
    exit 1
fi
# Readiness was checked above; do not restart the completed init services.
docker compose up -d --no-deps app
echo 'Кабинет запущен. Статус: docker compose ps; логи: docker compose logs -f app'
