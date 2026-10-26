Исторический документ

# AURELIUS workflow — модули 1–5 DEMO

Один диалоговый агент, LangGraph workflow и типизированные прикладные сервисы. LLM извлекает изменения; разрешения, переходы, финансовые расчёты и решения не определяются свободным текстом модели.

[Полное руководство: запуск, API, операторские команды и ограничения](../../../../docs/DEMO_MODULES_1_5.md). [Архитектура](../../../../DataAndArcBuild/architecture/00_architecture_overview.md).

## Состав

- [`../../rag`](../../rag/README.md): справочные ответы по 99 требованиям из `knowledge`, локальный FAISS и отдельный LangGraph-подграф; цитаты и SHA-256 источника, без изменения заявки.
- `agents/workflow.py`: состояния, уточнения, ревизии, явные команды и сохранение результата.
- `services/extraction_validation.py`: поэлементная проверка, цитаты и repair с сохранением неустранённых замечаний.
- `services/product_matching.py`, `database_modules.py`: 16 направлений, версии PostgreSQL для R01–R03 и явно подтверждённые правила.
- `services/data_preparation.py`, `questionnaire.py`, `documents.py`: источники с отсечкой, анкета, файлы и неизменяемый snapshot.
- `services/assessment.py`: registry, проверенные явные 16/23 входа и настоящий CatBoost; разные baseline PD и dynamic hazard.
- `services/lending.py`: ручное рассмотрение, предложение, отдельный DEMO-акцепт, идемпотентная симуляция исполнения/платежей.
- `repositories/`: PostgreSQL runtime/business и явная SQLite-совместимость; `schemas/`: Pydantic-контракты.
- `operator.py`: доверенные действия reviewer по входам, условиям, профилю, анкете и ручному решению; они недоступны borrower HTTP API.

## Запуск и данные

```sh
/Users/retro0/projects/PyVenv/venv_core/bin/python -m personalCab.prom.prom_lab.ai_agents_lab.database --init-workflow
/Users/retro0/projects/PyVenv/venv_core/bin/python -m personalCab.frontend.server --company-id 40
```

PostgreSQL настроить через `PG_*`/pgpass или `AURELIUS_DATABASE_URL`. Docker: `docker compose up --build -d`. Миграции additive, backup восстанавливается только в пустой том. Существующие данные/снимки сохраняются. Никакого молчаливого fallback в SQLite нет; `--database PATH` выбирает его явно для М1–М2/тестов.

## Повторы и границы

Advisory lock сериализует команды владельца, CAS защищает кейс, доменные case/receipt/audit фиксируются атомарно. Снимки, оценки и DEMO-операции имеют независимые устойчивые ключи для восстановления после частичного сбоя. Checkpoint не заменяет доменную запись и не гарантирует exactly-once внешнего сервиса.

Согласия и выбор компании задаются отдельными командами интерфейса в пределах операторского allowlist; роли/подтверждённость/одобрение не приходят из LLM. М3 не выводит неутверждённые ratios или единицы. М4 использует явно подтверждённый вектор, не seeded scores. М5 — ручной DEMO, без реальных денег, юридических подписей и автоматического одобрения синтетической моделью.

## Тесты

```sh
/Users/retro0/projects/PyVenv/venv_core/bin/python -m pytest personalCab/frontend/tests personalCab/prom/prom_lab/ai_agents_lab/tests -q
```

Fixtures заменяют Ollama. Проверки реального CBM не требуют обучения. HTTP требует локальных портов; `AURELIUS_TEST_DATABASE_URL` должен указывать отдельную seeded БД. Живая модель проверяется в браузере отдельно.
