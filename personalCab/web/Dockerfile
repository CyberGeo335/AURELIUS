# Актуальный кабинет v3. Build context: корень репозитория; target: runtime.
FROM node:24-alpine AS web
WORKDIR /web
COPY personalCab/web/package*.json ./
RUN npm ci
COPY personalCab/web/ ./
ARG VITE_API_MODE=http
RUN test "$VITE_API_MODE" = http && VITE_API_MODE="$VITE_API_MODE" npm run build

FROM python:3.13-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app
COPY requirements.txt requirements-dev.txt requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY scoring/ /app/scoring/
COPY personalCab/ /app/personalCab/
COPY knowledge/ /app/knowledge/
COPY deploy/ /app/deploy/
COPY start.sh start.ps1 /app/
COPY --from=web /web/dist /app/personalCab/web/dist
ENTRYPOINT ["python", "/app/deploy/runtime.py"]
EXPOSE 5173
CMD ["python", "-m", "personalCab.prom_v2.cabinet_server", "--host", "0.0.0.0", "--port", "5173"]

FROM runtime AS test
RUN pip install --no-cache-dir -r requirements-dev.txt && pip check
