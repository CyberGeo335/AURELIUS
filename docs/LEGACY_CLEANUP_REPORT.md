# Очистка легаси AURELIUS

Дата: 2026-10-26. База: свежая `origin/test-dev`, `40b8038`. Ветка: `chore/cleanup-legacy`. Push не выполнялся.

## Базовая линия и результаты

| Проверка | До | После |
|---|---|---|
| Tracked-файлы | 2263 | 2161 |
| Суммарный размер tracked-файлов (байты, не размер .git) | 585054078 | 582872228 |
| Python: scoring/main/tests + prom_v2/tests + deploy/tests, без БД | 97 passed, 55 skipped, 3 failed | 79 passed, 30 skipped, 0 failed |
| Cabinet + scoring DatabaseTests на отдельной seeded БД (кабинет первым) | 30 passed | 30 passed в составе полного прогона |
| Полный сохранённый Python-набор с БД и prom_lab | — | 124 passed, 0 skipped, 0 failed |
| prom_lab, весь исходный набор | 103 passed, 16 skipped, 5 failed | сохранённые тесты: 15 passed |
| Фронт: npm ci, lint, test, VITE_API_MODE=http build | успешно; 257 tests / 16 files | lint/test/build успешно; 225 tests / 13 files |
| SHA-256 защищённых файлов scoring/main | сохранён вне репозитория | совпал байт в байт |
| Docker app + tests | — | обе сборки успешны |
| Compose tests, штатная команда без AURELIUS_TEST_DATABASE_URL | — | 94 passed, 30 skipped, 0 failed |

Для Python использован `/Users/retro0/projects/PyVenv/venv_core/bin/python`. npm отсутствует на хосте: команды фронта выполнены в официальном `node:24-alpine`, с монтированием `personalCab/web`. Новые зависимости в проект не добавлялись. Предупреждения Python: три существующих FAISS SWIG DeprecationWarning.

Исходные три ошибки prom_v2/test_assessment связаны с отсутствующим registry.json и удалены вместе с этим контуром. В базовом prom_lab пять ошибок относятся к удалённому test_cabinet_modules. 18 ранее успешных и 25 пропускаемых тестов основного Python-прогона удалены; новых падений в сохранённых тестах нет. Во фронте удалены ровно три файла с 32 тестами.

Хэши: `/tmp/aurelius-cleanup-before.sha256`, `/tmp/aurelius-cleanup-after.sha256`; сравнение `cmp` успешно. В scoring/main перемещены только два Markdown-документа и один DOCX. Все .py/.json/.cbm вне tests/reports сохранены по содержимому и пути. `catalog/products.json` целиком сохранён без изменений.

## Этапы и коммиты

| Этап | Результат | Коммит |
|---|---|---|
| 1 | 60 перемещённых файлов; созданы history/README.md и MOVES.md; исправлены Markdown-ссылки технических документов | 861e6ca |
| 2 | 35 удалённых файлов: старый frontend, три компонента и их тесты, integrated.css, три дублирующих Docker/nginx-файла | 5356725 |
| 3 | 23 удалённых файла старого prom_v2; из repository.py удалён только PostgresRepository (74 строки) | 8157c26 |
| 4 | 29 удалённых файлов prom_lab; в Compose добавлен каталог сохранённых тестов | f77af50 |
| 5 | 16 удалённых файлов: v_1/v_2 дампы и схемы, логи CatBoost; убраны исключения для scoring/models в .dockerignore | 0c1d07d |
| 6 | Удалены Dockerfile.v2 и compose.v2.yaml; корневой Dockerfile не изменён | 705ded2 |

Презентация команды в tracked-файлах отсутствует. Локально есть 16-страничный PDF `Альфа_Хак_Умный_кредитный_кабинет.pdf` с постановкой кейса (бизнес-контекст, ограничения, критерии успеха), это не итоговая презентация AURELIUS; он не добавлялся в Git.

## Граф импортов и тесты prom_lab

Граф построен AST-обходом, включая Import/ImportFrom внутри функций, от cabinet_server, deploy/*.py, сохранённых prom_v2/scoring/deploy тестов. Для локальных относительных импортов рассчитаны полные имена; отдельно проверены динамические import_module/__import__ (в сохраняемом контуре отсутствуют). Сохранены package __init__.py, все schemas, agents/factory.py, services/{extraction_validation,product_matching,questionnaire,workflow_service}.py, repositories/{case_repository,business_repository}.py, catalog/products.json.

Workflow_service остаётся из-за ModuleUnavailable; business_repository — из-за ленивого импорта PRODUCT_CODES в questionnaire. Эти файлы не рефакторились. Сохранены tests/test_extractor.py и test_client_validation.py — 15 успешных тестов. test_product_matching.py импортирует WorkflowApp и test_workflow.ScriptedExtractor; test_requirements_rag.py — старый frontend и WorkflowApp. Оба файла не удовлетворяют условию «тестировать только живые модули» и удалены целиком, без переписывания и новых тестов. Сохранённые test_agent.py продолжают проверять RAG и подбор продуктов. Полный граф и исходный план доступны в `/tmp/aurelius-cleanup-graph.json`.

## Какие проверки удалены на этапе 3

| Удалённые тесты | Что проверяли | Аналог в test_cabinet.py |
|---|---|---|
| test_http, test_postgres | Владельцы, версии, replay request_id, восстановление старого PostgresRepository, отделение схем | ownership_version_and_idempotent_create и HTTP auth/origin; прямого аналога восстановления старой схемы нет |
| test_atomic_business | Атомарный rollback результата/снимка, сохранённый ответ при отказе источника | incomplete_submission_rolls_back, scoring_outage_retries_submission_without_duplicate_mutation; другой контур, не полное совпадение |
| test_web_server | Старый public_origin, внешний порт, отказ чужому Origin | http_origin_cookie_login_and_logout; старые комбинации public_origin больше не проверяются |
| test_workspace | Покрытие выписок по cutoff, дубликаты/будущие строки; ранний профиль с consent; реальный preview графика | employee_attestation_preserves_source_facts и документы проверяют часть поведения; прямых аналогов старого profile/preview/statement parser нет |
| test_workspace_database | Назначенный reviewer, аудит trusted profile resolution | concurrent_assignment_and_release_permissions, employee_attestation_preserves_source_facts; старого profile resolution нет |
| test_workspace_http | Каталог 16 направлений, ранний профиль, актуальность документов, reviewer/preview/audit, model explanation, source conflict | document_bytes_scope_retry_and_open_request, assignment, real scorer и client redaction; нет полного аналога старых endpoint/SHAP/preview сценариев |
| test_integrated_web | Сквозной старый M1–M5, сессии, consent, версии/replay, отмена offer при смене evidence, R02/R03 demo execution | ownership/version/idempotency, actual_scorer_result_review_accept_and_client_redaction (включая изменение источников), document scope; старые demo execution/R02/R03 сценарии не сохранены |
| test_follow_up_and_recovery | Ответы на запросы, документы, адресные уточнения, приватное durable recovery и replay | document_bytes_scope_retry_and_open_request и retry submission покрывают часть; прямого старого durable recovery нет |
| test_assessment | Реальный SHAP, реконструкция monthly logit и отказ объяснения без потери assessment | Прямого SHAP-аналога нет; actual_scorer проверяет реальный скоринг, review/accept/redaction |

Оставшийся test_agent.py отдельно сохраняет изоляцию субъектов, версии и receipt replay, rollback неудачной транзакции, consent и валидацию extraction. Эти проверки не считаются заменой удалённых интеграционных сценариев один к одному. Новых тестов не написано.

## Проверка отдельного развёртывания

Использован только проект `aurelius_cleanup_test`: volume `aurelius_cleanup_test_postgres_data`, PostgreSQL 55439, приложение 55179. Исходный дамп восстановлен штатным entrypoint только на новом томе. Основной том `aurelius_postgres_data` не монтировался и не изменялся. Тестовые БД `aurelius_test_cleanup` и `aurelius_test_cleanup_final` созданы отдельно внутри этого контейнера; исходная business-БД предназначена для smoke, не для pytest.

`docker compose --profile tools build app tests` успешен; обе цели построены по неизменённому корневому Dockerfile. `docker compose --profile tools run --rm tests`: 94 passed / 30 skipped. Приложение и БД healthy. Повторный up на том же томе: `Initial seed already validated; existing business data preserved.`; миграции 005–009 успешны, дамп повторно не восстанавливался.

В браузере проверена отрисовка страницы входа на http://127.0.0.1:55179/. На этом же развёрнутом стенде HTTP smoke подтвердил CLIENT login, BANK_EMPLOYEE login, создание черновика и одно сообщение живой Ollama. Подача, реальный скоринг, review и принятие проверены автоматическими интеграционными тестами кабинета на отдельной тестовой БД; вручную через браузер весь этот путь не пройден. Скрипты smoke хранят учётные данные только в памяти, в Git паролей нет.

### Ограничение тестового набора, не исправлялось

Полный повторный pytest на ранее использованной тестовой БД дал 8 failures `Missing DB risk policy version`: test_database.py:test_application_id_only_builds_features_without_external_context (cleanup на строках 251–252) удаляет seed policy и macro indicator. Поэтому БД после этого набора нельзя считать исходной seeded БД. Финальный успешный прогон выполнен на новой копии seed с порядком cabinet → deploy → prom_lab → scoring; 124 passed. Финансовая логика, тесты и seed_policy не исправлялись. Это отдельная задача по изоляции тестовых фикстур.

Повторяемые команды (из корня, существующий .env):

```sh
COMPOSE_PROJECT_NAME=aurelius_cleanup_test POSTGRES_PORT=55439 APP_PORT=55179 docker compose --profile tools build app tests
COMPOSE_PROJECT_NAME=aurelius_cleanup_test POSTGRES_PORT=55439 APP_PORT=55179 docker compose --profile tools run --rm tests
COMPOSE_PROJECT_NAME=aurelius_cleanup_test POSTGRES_PORT=55439 APP_PORT=55179 docker compose up -d
COMPOSE_PROJECT_NAME=aurelius_cleanup_test POSTGRES_PORT=55439 APP_PORT=55179 docker compose logs init
```

Для полного DB-прогона направить AURELIUS_TEST_DATABASE_URL на свежую seeded БД с именем aurelius_test*, затем:

```sh
PYTHONPATH=$PWD/scoring:$PWD /Users/retro0/projects/PyVenv/venv_core/bin/python -m pytest personalCab/prom_v2/tests deploy/tests personalCab/prom/prom_lab/ai_agents_lab/tests scoring/main/tests -q -p no:cacheprovider -rs
```

## Ссылки для Данила

MOVES.md готов: [таблица всех перемещений](history/MOVES.md). Защищённые документы не изменены. docs/01…09, docs/api и THIRD_PARTY_NOTICES.md в исходной ветке отсутствуют; не создавались.

| Файл:строка | Что обновить |
|---|---|
| README.md:74 | Упоминание удалённого старого web_server/frontend |
| README.md:75 | compose.v2.yaml удалён; основной compose.yaml сохранён |
| README.md:76 | Dockerfile.v2 и personalCab/web/Dockerfile удалены |
| README.md:152 | docs/CABINET_V3.md → docs/history/reports/CABINET_V3.md |
| AGENTS.md:5 | Удалённый personalCab/frontend |
| AGENTS.md:7 | Описание старого M1–M5/prom_lab требует актуализации |
| AGENTS.md:8 | DataAndArcBuild → docs/history/architecture; POSTGRES_INTEGRATION → history/reports |
| AGENTS.md:9 | DEMO_MODULES_1_5 → history/reports; исторический статус модулей |
| AGENTS.md:27–30 | Удалённые requirements.txt, database CLI, frontend server/tests |
| AGENTS.md:41 | Историческое описание frontend/workflow тестов |

Дополнительные ссылки в оставленных рядом с кодом README (сами файлы не менялись): scoring/main/README.md:76,77,153,197 — INTEGRATION, MODEL_REPAIR, README_versions; personalCab/prom/rag/README.md:47,50 — удалённые requirements и test_requirements_rag.

Финальный git grep по удалённым путям не обнаружил ссылок в сохраняемом коде/тестах/Docker/скриптах, кроме согласованного исключения: `catalog/products.json:3`, историческая provenance source. Её изменение изменило бы context_hash, поэтому старые пути оставлены по явному решению пользователя. Исторические документы закономерно содержат старые ссылки. `git diff --check` успешен.

## Вопросы и оставшиеся задачи команды

Блокирующих вопросов нет. Данилу: актуализировать перечисленные ссылки и AGENTS v3. Егору: отдельно исправить изоляцию seed policy в test_database и выполнить ручной browser smoke подачи/скоринга при необходимости. Итоговую презентацию команды ещё нужно предоставить. Ранее выделенные дефекты request_id, reasons и Origin этим прогоном не исправлялись. Данные/ноутбуки/эксперименты Евы и seeds сохранены. Публикация ветки и PR не выполнялись.
