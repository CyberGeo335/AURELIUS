# AURELIUS · агент V2

> Актуальное продолжение: [интегрированный V2 DEMO](../../docs/V2_INTEGRATED_DEMO.md). Серверный вход, WEB и бизнес-адаптеры M3–M5 подключены. Ниже сохранено описание этапа ядра 0.1.

Новая реализация диалогового ядра для WEB V2. V1 (`personalCab/prom`, `personalCab/frontend`, `DataAndArcBuild/architecture`) сохраняется. Новый workflow не вызывает V1 WorkflowApp/ChatService и не записывает его кейсы.

Архитектура: [architecture_v2](../../DataAndArcBuild/architecture_v2/README.md). [Результаты проверки](VALIDATION.md).

## Что работает

- Собственный LangGraph: выбор ветки, исполнение явной команды, построение типизированного ответа.
- Общий серверный запрос для чата и формы; чат сначала сохраняет предложение с цитатами, затем ждёт CONFIRM_FACTS.
- Обязательные case_id/expected_version; revision отдельно от версии агрегата; защита устаревших предложений и конкурентных вкладок.
- Pydantic и проверка текущей цитаты, один repair, пригодные соседние поля, сохранение прежнего значения при неверной правке, DataResolutionPlan.
- Каталог 16 направлений, явные отображения term/R01, rcl/R02, overdraft/R03, отсутствие fallback на R01.
- RAG на существующих FAISS/LangGraph и knowledge JSON, структурированные цитаты и SHA-256; работает без Ollama и не меняет параметры кейса. Последний справочный ответ сохраняется в last_knowledge_answer для восстановления.
- Явные CANCEL/create/list/state; PostgreSQL-сохранение V2, квитанции и аудит; memory только по запросу.
- Локальный API `/api/v2` с токеном, привязанным к серверному профилю, и отдельный CLI.

## Граница версии 0.1

Это первая работающая реализация нового ядра. **WEB V2 пока не переключён на него.** Consent registry, бизнес-документы/анкета/snapshot, actual M4/M5 и операторский API V2 пока не подключены. Команды этих этапов возвращают SERVICE_NOT_CONFIGURED; задача отмечается ENGINEERING. Финансовое решение и PD не имитируются.

Реестр пяти scope в коде задаёт контракт проверки доверенных grants, а не готовую выдачу/отзыв через новый кабинет. Локальный gateway не получает consent/роль/компанию из HTTP-тела. У него нет клиентского login/logout или производственной IAM. Права сотрудника не создаются флагом в запросе.

При отсутствии Ollama можно пользоваться формой и RAG. При ошибке PostgreSQL нет перехода на memory/SQLite. Старые localStorage/кейсы не импортируются. Код не исправляет CSV WEB автоматически и не меняет его финансовые константы.

## Зависимости и запуск

Из корня репозитория, в общей среде:

```sh
PY=/Users/retro0/projects/PyVenv/venv_core/bin/python
$PY -m pip install -r personalCab/prom_v2/requirements.txt
```

Зависимости совпадают с проверенным набором V1. Переиспользуются библиотечные схемы/валидация/каталог/RAG/config, перечисленные в `adapters.py` и архитектурных ADR. Физически автономная поставка без каталога `personalCab/prom` пока не поддерживается. В V1 ничего не устанавливается и не изменяется программно, но Python-среда общая.

### Справочный вопрос без модели и БД

```sh
$PY -m personalCab.prom_v2 --memory \
  --actor-id demo-v2 --company-id 40 --borrower-id demo-business-40 \
  --question 'Какой формат ИНН для R01 ООО?'
```

Actor задаётся оператором запуска, а не пользователем чата. Это синтетический временный процесс, не реальный вход клиента. JSON содержит knowledge_answer, citations/source_sha256, request и version/revision.

### PostgreSQL

Настройте отдельный `AURELIUS_V2_DATABASE_URL` или обычные PG-переменные. Если V2 URL не задан, используется `AURELIUS_DATABASE_URL`/PG config; всегда создаётся/используется только схема `aurelius_agent_v2` для ядра. Для отдельного окружения предпочтителен V2 URL. Host Python не загружает `.env` автоматически.

```sh
$PY -m personalCab.prom_v2 --init-db
$PY -m personalCab.prom_v2 \
  --actor-id demo-v2 --company-id 40 --borrower-id demo-business-40
```

Второй запуск читает JSONL-команды из stdin. Добавьте `--with-ollama` для извлечения через `gpt-oss:20b`; адрес задаётся OLLAMA_BASE_URL. Инициализация только добавочная: не восстанавливает backup, не создаёт клиентов и не меняет `public` или `aurelius_workflow`.

### Локальный HTTP gateway

```sh
export AURELIUS_V2_API_TOKEN="$($PY -c 'import secrets; print(secrets.token_urlsafe(32))')"
$PY -m personalCab.prom_v2 --memory --serve --with-ollama \
  --actor-id demo-v2 --company-id 40 --borrower-id demo-business-40 --port 5180
```

Для долговечного режима уберите --memory после явного init-db. Токен не печатается сервером и не сохраняется в репозитории. Не помещайте его в URL, Vite bundle или localStorage. У работающего WEB :5175 нет автоматического доступа к этому gateway; будущий session/BFF-адаптер описан в [WEB/API архитектуре](../../DataAndArcBuild/architecture_v2/05_web_and_api.md).

## Контракт API

Все запросы требуют `Authorization: Bearer <token>` и разрешённый локальный origin/host.

| Метод | Путь | Назначение |
| --- | --- | --- |
| GET | `/api/v2/health` | Версия и возможности; extraction_configured не обещает доступный Ollama |
| GET | `/api/v2/cases` | Кейсы привязанного владельца/компании |
| GET | `/api/v2/cases/{case_id}` | Восстановление состояния и истории |
| POST | `/api/v2/commands` | Типизированная команда, ответ View |

Создать кейс:

```json
{"request_id":"new-001","action":"CREATE","expected_version":0}
```

Вернувшиеся case_id/version использовать в следующем запросе:

```json
{
  "request_id":"form-001",
  "action":"UPDATE_REQUEST",
  "case_id":"V2-<returned-id>",
  "expected_version":1,
  "arguments":{"patch":{"legal_form":"IP","purpose":"INVENTORY","amount_rub":1500000,"term_months":12}}
}
```

Чат: `action=CHAT`, `text`, без arguments. Подтверждение: `action=CONFIRM_FACTS`, `arguments={"proposal_id":"PROP-..."}`. Выбор: SELECT_PRODUCT с `product_id` из полученных кандидатов; не русская подпись и не выдуманный R01 fallback. Очистка поля — `clear_fields`, а не null в patch. borrower_id не редактируется.

Повтор после потерянного ответа отправляет исходный payload/ID/version. После 409 из-за изменения кейса перечитайте состояние и создайте новую команду. Сохранённый receipt может описывать более раннюю version, чем текущий GET; это результат исходной операции, а не откат состояния.

## Тесты

```sh
$PY -m pytest personalCab/prom_v2/tests -q
$PY -m pytest personalCab/frontend/tests personalCab/prom/prom_lab/ai_agents_lab/tests -q
```

HTTP требует доступа к loopback. `test_postgres.py` пропускается, если AURELIUS_TEST_DATABASE_URL не задан. Для его запуска используйте только отдельную seeded тестовую БД: тест добавляет V2-схему/записи, проверяет replay после нового экземпляра Agent и отсутствие кейса в V1. Чужие таблицы не очищаются. Рабочая БД не является тестовой.

Отдельный живой smoke без записи в PostgreSQL (нужна работающая gpt-oss:20b):

```sh
$PY -m personalCab.prom_v2.tests.live_model_check
```

## Структура

```text
models.py       новые Command/Actor/Case/Proposal/View
agent.py        независимая V2 orchestration
adapters.py     извлечение, read-only каталог и RAG
ports.py        интерфейсы извлечения/справки/продуктов/M3–M5
repository.py   отдельные PostgreSQL/memory repositories
server.py       локальный scoped-token gateway
__main__.py     явные режимы CLI/init/HTTP
migrations/     только V2 SQL
tests/          доменные, HTTP и opt-in PostgreSQL проверки
```
