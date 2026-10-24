FROM python:3.13-slim
WORKDIR /app
COPY personalCab/prom/prom_lab/ai_agents_lab/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY personalCab /app/personalCab
COPY knowledge /app/knowledge
COPY scoring/bd/migrations /app/scoring/bd/migrations
COPY scoring/models/registry.json /app/scoring/models/registry.json
COPY scoring/models/experiments/survival_v2_baseline/catboost_hazard.cbm /app/scoring/models/experiments/survival_v2_baseline/catboost_hazard.cbm
COPY scoring/models/experiments/survival_v2_dynamic/catboost_dynamic_hazard.cbm /app/scoring/models/experiments/survival_v2_dynamic/catboost_dynamic_hazard.cbm
ENV PYTHONUNBUFFERED=1
EXPOSE 5173
CMD ["python", "-m", "personalCab.frontend.server", "--host", "0.0.0.0"]
