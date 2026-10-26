Исторический документ

# Docker: границы интеграций

Основной путь — `personalCab.prom_v2.cabinet_server`, единый same-origin сервер.
Python 3.13; прямые зависимости в корневом requirements.txt, транзитивные версии
зафиксированы requirements.lock.txt; инструменты тестирования — requirements-dev.txt.
matplotlib/scipy/plotly присутствуют как обязательные зависимости CatBoost,
а не как подключение исследовательского scoring/requirements.txt.

| Интеграция | Код | Подготовка в Docker |
|---|---|---|
| PostgreSQL 17 v3 | deploy/00_restore.sh | pg_restore только в пустой PGDATA, --no-owner/--no-privileges; том сохраняется |
| Начальные количества | deploy/initialize.py | 30 компаний, 30 заявок, 32 пользователя, 3 политики, 1 макропоказатель; отметка в aurelius_deploy |
| Миграции | cabinet.py initialize | Только 005–009, повторяемые; public не изменяется миграциями |
| Вход | cabinet.py login/session | public.user_accounts; cookie и служебные сессии в PostgreSQL |
| Заявки | cabinet.py action | public v3 плюс aurelius_cabinet; отдельного backend не требуется |
| Скоринг | cabinet.py _score → scoring/main/database.py | scoring автоматически добавляется в sys.path; модель и policy.demo.json копируются без изменений |
| Фронт | personalCab/web + cabinet_server.py | npm ci, HTTP build, --root personalCab/web/dist; внутренний порт 5173 |
| Документы | cabinet_documents.py, миграция 006 | bytea в БД; файлового тома нет |
| Диалоги | cabinet_assistant.py, миграция 009 | PostgreSQL, Agent V2 с теми же границами подтверждения |
| Ollama | adapters.py | Endpoint выбирает start.sh/start.ps1; model-init проверяет tags, pull и generate; app ждёт успеха |
| RAG | personalCab/prom/rag/index.py | FAISS/NumPy, knowledge/; лексический индекс в памяти |
| Healthcheck | deploy/healthcheck.py | Статика 200 и ожидаемая 401 от неавторизованной session |

Старые frontend/server и prom_v2.web_server не запускаются. Их чтение имени модели
унифицировано через OLLAMA_MODEL, но финансовое/прикладное поведение не менялось.
Нет отдельной БД aurelius_v2. Все сохранённые Dockerfile собирают текущий кабинет;
compose.v2.yaml включает основной Compose.

## Настройки

- POSTGRES_DB/USER/PASSWORD из .env → db и PG_DATABASE/USER/PASSWORD приложения.
- PG_HOST=db, PG_PORT=5432 — внутренняя сеть; POSTGRES_PORT — loopback хоста.
- deploy/runtime.py собирает DATABASE_URL (SQLAlchemy) и AURELIUS_DATABASE_URL
  (psycopg) из тех же частей, экранируя пользователя/пароль/имя БД.
- OLLAMA_BASE_URL — внешний адрес; временный OLLAMA_ENDPOINT скрипт задаёт только
  при fallback на http://ollama:11434. Пользователю вручную его сохранять не нужно.
- OLLAMA_MODEL — единое имя для всех трёх адаптеров.
- VITE_API_MODE=http — только сборка; не переопределяет окружение mock-тестов.
- APP_BIND_HOST/APP_PORT — публикация кабинета.
- AURELIUS_MODEL_PATH/FEATURES_PATH/MODEL_CONFIG_PATH поддерживаются самим scoring;
  стандартные артефакты уже включены по штатным путям.
- AURELIUS_TEST_DATABASE_URL — только выделенная seeded тестовая БД aurelius_test*.

Legacy-переменные AURELIUS_V2_DATABASE_URL/API_TOKEN, V2_PUBLIC_ORIGIN и
DEMO-компании/согласия не нужны основному запуску. libpq PGHOST/PGPORT и остальные
fallback-имена сохраняются в исходном коде, но в Compose не дублируются.

Seed-скрипты не запускаются: аккаунты уже в дампе. В seed_user_accounts.py удалены
захардкоженные параметры соединения и ошибочное чтение переменной admin; в
seed_test_data.py удалён fallback-пароль admin. Для ручного запуска задавать PG_*.
.env и generated_credentials.csv исключены из Git и Docker context.

HTTPS-прокси не настраивается. В текущем HTTP-обработчике ожидаемый Origin строится
с http://Host; для HTTPS требуется отдельная согласованная настройка приложения.
