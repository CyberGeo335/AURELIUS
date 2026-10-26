# 08. Тестирование

Проверено на коммите `40b8038` (ветка `test-dev`).

Здесь собрано, что и чем проверяется в текущей версии (кабинет v3), и фактические результаты прогонов на стенде. Как запускать тесты — [09-deployment.md](09-deployment.md#9-автотесты-в-docker). Демо-пути для ручной проверки — [03-demo-scenarios.md](03-demo-scenarios.md).

## 1. Что тестируется

| Набор | Где | Как запускается | Что покрывает |
|---|---|---|---|
| Python, скоринг | `scoring/main/tests` | `pytest` в сервисе `tests` (профиль `tools`) | конвейер расчёта, предсказатель, пакетный отчёт; работа с БД — только с отдельной тестовой БД |
| Python, кабинет и ассистент | `personalCab/prom_v2/tests` | то же | ядро кабинета v3 (`test_cabinet.py`, только с отдельной тестовой БД), документы, Agent V2 ассистента; плюс тесты прежнего V2 |
| Python, запуск | `deploy/tests` | то же | сборка строк подключения, пустой пароль, готовность Ollama, поведение `start.sh` |
| Фронт | `personalCab/web/src/test` | `npm test` (Vitest) в образе стадии `web` | HTTP-клиент, анкета по шагам, трек этапов, очередь, журналы, видимость причин, ассистент; плюс тесты mock-режима и прежних экранов V2 |
| API | `docs/api/aurelius.postman_collection.json` | newman в сети стенда | сквозной сценарий, отмена, негативные проверки, ожидаемая ошибка на дампе ([06-api.md](06-api.md#6-коллекция-запросов)) |
| Контракт API | `docs/api/openapi.yaml` | `npx @redocly/cli lint`; проверка ответов стенда схемами | валидность описания и совпадение ответов `session`, `state`, ошибок со схемами |
| UI | `tmp`-скрипт Playwright (вне репозитория) | Chromium в Docker в сети стенда | прохождение демо-путей через интерфейс со скриншотами ([03-demo-scenarios.md](03-demo-scenarios.md)) |

### 1.1. Python-тесты по файлам

155 тестов (посчитано `pytest --collect-only`).

| Файл | Тестов | К чему относится | Без тестовой БД |
|---|---:|---|---|
| `personalCab/prom_v2/tests/test_cabinet.py` | 20 | кабинет v3: миграции, вход и cookie, `Origin`, владение и версии, квитанции, откат неполной подачи, проверки сотрудника, повтор после сбоя скоринга, реальный скоринг → `APPROVE` → `accept` → `OFFER_STALE`, блокировки входов, документы, назначения, ассистент | пропускаются (нужна `AURELIUS_TEST_DATABASE_URL`) |
| `personalCab/prom_v2/tests/test_cabinet_documents.py` | 11 | проверка PDF и CSV | выполняются |
| `personalCab/prom_v2/tests/test_agent.py` | 27 | Agent V2 ассистента (извлечение, подтверждение, справочные вопросы) | выполняются |
| `scoring/main/tests/test_pipeline.py` | 22 | конвейер скоринга и подбор условий | выполняются |
| `scoring/main/tests/test_predictor_semantics.py` | 7 | семантика модели CatBoost | выполняются |
| `scoring/main/tests/test_batch.py` | 2 | пакетный отчёт | выполняются |
| `scoring/main/tests/test_database.py` | 10 | `run_application` с записью в БД, идемпотентность, откат | пропускаются (нужна `AURELIUS_TEST_DATABASE_URL`) |
| `deploy/tests/test_launch.py` | 10 | `deploy/runtime.py`, `ollama_ready.py`, `start.sh` | выполняются |
| прежний V2: `test_assessment.py` (3), `test_http.py` (3), `test_web_server.py` (5), `test_workspace.py` (10), `test_workspace_http.py` (8), `test_workspace_database.py` (2), `test_atomic_business.py` (2), `test_integrated_web.py` (8), `test_follow_up_and_recovery.py` (4), `test_postgres.py` (1) | 46 | `prom_v2/server.py`, `web_server.py`, рабочее пространство V2, SHAP-объяснения V2, БД `aurelius_v2` | частично выполняются, частично пропускаются (нужны отдельные переменные V2) |

Тесты, которые работают с PostgreSQL, запускаются только при явной переменной (`AURELIUS_TEST_DATABASE_URL`, `AURELIUS_V2_ATOMIC_TEST`) и проверяют, что имя БД начинается с `aurelius_test`. Рабочую БД они не трогают.

### 1.2. Тесты фронта по файлам

257 тестов в 16 файлах (по отчёту Vitest).

| Группа | Файлы и число тестов | Всего |
|---|---|---:|
| Текущий HTTP-режим | `server_stage` (72), `http_form_steps` (25), `http_credit` (20), `client_home` (20), `http_assistant` (13), `http_provenance` (12), `http_journals` (9), `http_queue` (6) | 177 |
| Общие доменные функции | `domain` (8) | 8 |
| Mock-режим и прежние экраны V2 | `integrated` (18), `screens` (14), `auth` (11), `mock` (10), `server_screens` (10), `chat` (5), `case_forms_v2` (4) | 72 |

Группы определены по импортам файлов: `HttpCreditApi` и `src/domain/*` — текущий путь; `MockCreditApi`, `IntegratedCabinet`, `ServerPages`, `HttpChatApi` (`/api/chat`) — прежний.

## 2. Результаты прогонов

Все прогоны — 26.10.2026 на стенде из чистой копии `40b8038` (Windows, Docker Desktop, Linux-контейнеры; Compose-проект `aurelius-docs`), командами из [09-deployment.md](09-deployment.md#9-автотесты-в-docker). Логи — `tmp\docs-stage4-run.log`, `tmp\docs-stage3-newman.log` (вне репозитория).

| Набор | Команда | Итог | Время |
|---|---|---|---|
| Python | `docker compose --profile tools run --rm --no-deps tests python -m pytest scoring/main/tests personalCab/prom_v2/tests deploy/tests -q -p no:cacheprovider -rfs` | 155 тестов: **97 passed, 3 failed, 55 skipped** | 8,85 с |
| Фронт | `docker build --target web -t aurelius-web-test .` + `docker run --rm aurelius-web-test npm test` | 16 файлов, **257 passed** из 257 | 9,80 с |
| API (newman) | `postman/newman:6.1.3`, коллекция `docs/api/aurelius.postman_collection.json`, `baseUrl=http://app:5173` | 69 запросов, **136 проверок, 0 упавших** | 5,4 с |
| OpenAPI | `npx @redocly/cli lint docs/api/openapi.yaml` (1.34.5 и 2.71.0) | valid, 1 warning `info-license` | — |
| Ответы API и схема | ответы `state` стенда (клиент и сотрудник, 4 снимка), проверка схемой `State` (jsonschema, Draft 2020-12) | 0 расхождений | — |

Python-тест отличается от стандартной команды из `compose.yaml` только флагом отчёта `-rfs` (список упавших и причин пропуска).

### 2.1. Упавшие Python-тесты

Все три — в `personalCab/prom_v2/tests/test_assessment.py`, то есть в тестах прежнего V2-сервиса `ExplainableAssessmentService` (SHAP-объяснения). Кабинет v3 этот модуль не импортирует: он используется только в `personalCab/prom_v2/integration.py` прежнего V2.

| Тест | Ошибка |
|---|---|
| `test_real_shap_reconstructs_monthly_logit_without_changing_probability[baseline]` | `KeyError: 'horizon_months'` |
| `test_real_shap_reconstructs_monthly_logit_without_changing_probability[dynamic]` | `KeyError: 'horizon_months'` |
| `test_explanation_failure_is_explicit_and_preserves_real_assessment` | ожидался статус `DEMO_ESTIMATE`, получен `TECHNICAL_ERROR` |

По решению владельца на этапе 5 тесты оставлены с этим пояснением; код и тесты в документационном этапе не менялись.

Тот же результат (97 / 3 / 55) получен и вне Docker, в облачной среде на Python 3.13 с теми же `requirements.lock.txt`.

### 2.2. Пропущенные Python-тесты

| Причина пропуска | Файлы | Тестов |
|---|---|---:|
| нет `AURELIUS_TEST_DATABASE_URL` — отдельной тестовой БД v3 | `test_cabinet.py` (20), `scoring/main/tests/test_database.py` (10) | 30 |
| прежний V2: нет отдельной БД или развёртывания V2 (`AURELIUS_TEST_DATABASE_URL`, `AURELIUS_V2_ATOMIC_TEST`) | `test_integrated_web.py` (8), `test_workspace_http.py` (8), `test_follow_up_and_recovery.py` (4), `test_atomic_business.py` (2), `test_workspace_database.py` (2), `test_postgres.py` (1) | 25 |

Значит, в обычном прогоне не выполняются интеграционные тесты ядра кабинета v3 и записи скоринга в БД. Что они проверяют — в разделе 1.1.

> TODO: внести результат прогона `tmp\docs-stage4-itest.cmd` на отдельной БД `aurelius_test_docs` после получения лога. Владелец разрешил прогон на этапе 5; выполнение и удаление тестовой БД пока не подтверждены. Основная БД не предназначена для этих тестов.

### 2.3. Сквозной прогон API

Подробно — [06-api.md](06-api.md#6-коллекция-запросов). Ключевые результаты:
- полный путь клиента и сотрудника до `REJECTED` с причиной `BANK_REJECT`, документ CSV скачан сотрудником без искажений;
- скоринг на исходном дампе: `MANUAL_REVIEW` с причиной `DB_INPUTS_UNAVAILABLE` («DB proxy needs 13 complete positive-revenue months; no zero-filling missing history»), PD нет;
- негативные проверки: 401 без сессии и при неверном пароле, 403 чужой `Origin`, 403 не та роль, 403 `ASSIGNEE_REQUIRED`, 409 `STALE_CASE_VERSION`, 409 `REQUEST_ID_REUSED`, 409 повторной отмены и `claim` черновика, 409 на `review APPROVE` без предложения.

### 2.4. Прохождение через интерфейс

Скрипт Playwright 1.63.0 (Chromium, `node:24-bookworm` в сети стенда, вне репозитория: `tmp\docs-stage4-shots\demo-screenshots.js`) прошёл пути 1–6 из [03-demo-scenarios.md](03-demo-scenarios.md) через интерфейс и снял 24 скриншота. Итог успешного прогона 26.10.2026 14:43–14:46: все шаги выполнены, код выхода 0.

| Что проверено | Результат |
|---|---|
| вход клиента и сотрудника через форму | роль и компания определены сервером |
| «Отправить заявку» | заявка `UNDER_REVIEW`, скоринг выполнен, клиент видит «Решение ещё не принято.» |
| «Взять в работу», «Повторить скоринг», «Зафиксировать проверку» | ответственный назначен, повторный расчёт, запись проверки в журнале |
| «Сохранить решение»: дозапрос и отказ | `AWAITING_DATA`, затем `REJECTED`; клиент видит только причину сотрудника |
| загрузка CSV к дозапросу, «Отправить ответ» | документ `STORED_UNVERIFIED`, заявка снова `UNDER_REVIEW` |
| сообщение помощнику, «Подтвердить предложенные изменения» | ответ `gpt-oss:20b` за 91 с; сумма, срок и цель с цитатами перенесены в анкету |
| «Отменить заявку» | `CANCELLED` |

Предыдущие попытки этого прогона нашли ограничение интерфейса. Если открыть кабинет по `http://<адрес не loopback>`, кнопка «Отправить заявку» показывает ошибку `crypto.randomUUID is not a function` и действие не выполняется. Причина: `crypto.randomUUID()` доступен браузеру только в безопасном контексте. Поэтому скрипт открывает кабинет по `http://127.0.0.1:5173`, проброшенному внутри контейнера на `app:5173`, как это делает пользователь на своём ПК. Подробно — [03-demo-scenarios.md](03-demo-scenarios.md#8-известное-ограничение-интерфейса).

## 3. Требования кейса и чем они проверены

Требования — из `ABOUT.md` («Постановка задачи», «Технические требования к решению и формат сдачи», «Ограничения», «Минимальный сквозной кредитный путь»).

| Требование кейса | Чем проверено | Результат |
|---|---|---|
| Клиент выбирает продукт и проходит путь от заявки до результата | UI-прогон, пути 1, 3, 4; коллекция, папка 01 | пройдено до отказа с причиной |
| Банк обрабатывает заявку: этапы и модель решения | UI-прогон, путь 2; коллекция; `test_pipeline.py` (22) | пройдено; решение принимает сотрудник |
| Данные сохраняются, состояние отображается динамически | UI-прогон (статусы, трек, журнал после каждого действия); коллекция (`state` после каждого действия) | пройдено |
| Уточнение недостающих данных | UI-прогон, путь 3; коллекция, `REQUEST_DATA` → `upload` → `answer` | пройдено |
| Скоринг ≠ кредитное решение | коллекция и UI: скоринг возвращает `MANUAL_REVIEW`, статус меняет только сотрудник; `test_pipeline.py` | пройдено |
| Итог не бинарный: одобрение, отказ, запрос данных, иные условия | отказ и дозапрос — UI и коллекция; одобрение и принятие — `test_cabinet.py` (`test_actual_scorer_result_review_accept_and_client_redaction`) | отказ и дозапрос пройдены; одобрение на исходном дампе недоступно, тест требует отдельной БД (раздел 2.2) |
| Защита от устаревших и повторных действий | коллекция: 409 `STALE_CASE_VERSION`, 409 `REQUEST_ID_REUSED`; `test_cabinet.py` | на стенде проверено коллекцией |
| Роли и разграничение доступа | коллекция: 401, 403 `Origin`, 403 роль, 403 `ASSIGNEE_REQUIRED`; ответы `state` проверены по ролям (клиент не получает `assessment`, предложение, проверки) | пройдено |
| Запуск в Docker на обычном ПК | запуск стенда ([09-deployment.md](09-deployment.md#12-результаты-проверки-запуска)); `deploy/tests` (10) | пройдено на Windows + Docker Desktop |
| Закреплённые версии | `requirements.lock.txt` + `pip check` при сборке; `npm ci` по `package-lock.json`; digest образа Ollama | сборка образов на стенде прошла |
| README, архитектура, API, OpenAPI, коллекция, диаграмма состояний, модель данных, тестовые сценарии | [README](../README.md), [05](05-architecture.md), [06](06-api.md), [openapi.yaml](api/openapi.yaml), [коллекция](api/aurelius.postman_collection.json), [04](04-credit-process.md#3-диаграмма-состояний-заявки), [07](07-data-model.md), этот файл и [03](03-demo-scenarios.md) | есть; OpenAPI проходит lint; коллекция прогнана |
| Синтетические данные и тестовые учётки | сверка числа строк с `manifest.json` ([07-data-model.md](07-data-model.md#61-контрольные-числа)) | 27 таблиц совпадают, 8 отличаются только на тестовые заявки |
| Только модели с открытыми весами | ассистент — `gpt-oss:20b` через Ollama; UI-прогон, путь 5 | ответ модели получен на стенде |
| Сценарий внутри продукта, без почты и SMS | UI-прогон: все шаги в кабинете | пройдено |
| Веб-интерфейс | UI-прогон в Chromium, тесты фронта (257) | пройдено |

## 4. Что не проверено

| Что | Почему |
|---|---|
| Положительный путь «PD → одобрение → принятие» на стенде | на исходном дампе нет 13 месяцев выручки ([02-decisions.md](02-decisions.md#ограничения-текущей-версии)); тест с собственной синтетической компанией требует отдельной БД |
| Интеграционные тесты v3 (`test_cabinet.py`, `scoring/main/tests/test_database.py`) на стенде | требуют отдельной БД `aurelius_test*` (раздел 2.2) |
| Полный набор тестов прежнего V2 | часть выполнена, часть пропущена; 3 выполненных теста падают (разделы 2.1–2.2); этот контур не является текущим кабинетом v3 |
| Нагрузка и параллельная работа нескольких сотрудников | не проводились. Конкурентное назначение проверяет только `test_cabinet.py` |
| Качество извлечения ассистента | один пример на стенде (путь 5). Набора диалогов для оценки нет — план развития ([02-decisions.md](02-decisions.md#план-развития)) |
| Работа по HTTPS и с других компьютеров | HTTPS не настроен; по HTTP не на loopback интерфейс не выполняет действия (раздел 2.4) |
| Linux, macOS, NVIDIA | на этом коммите запуск проверен только на Windows ([09-deployment.md](09-deployment.md#12-результаты-проверки-запуска)) |
