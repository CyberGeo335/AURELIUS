# AURELIUS — умный кредитный кабинет предпринимателя

Прототип цифрового кредитного конвейера для малого и микробизнеса, сделанный на хакатоне Альфа-Банка «Альфа Будущее». В одном веб-продукте собраны путь клиента и обработка заявки в банке: от черновика заявки до решения сотрудника и принятия предложения. Все данные синтетические, доступа к системам банка нет.

Проверено на коммите `40b8038` (ветка `test-dev`).

## Для кого

- **Клиент** — представитель ИП или ООО, оформляющий кредит от имени компании.
- **Сотрудник банка** — рассматривает заявки: запускает скоринг, проверяет сведения, запрашивает данные и принимает решение.

## Что умеет текущая версия

Клиент:
- входит по логину и паролю из БД; роль и компания определяются сервером;
- создаёт заявку на один из продуктов R01–R03, заполняет анкету по требованиям продукта, подтверждает сведения и отправляет заявку;
- в черновике может описать потребность ассистенту (`gpt-oss:20b` через Ollama). Ассистент предлагает значения полей с цитатами из сообщения, а в анкету они попадают только после явного подтверждения;
- отвечает на дозапрос банка текстом и файлом PDF или CSV;
- видит статус заявки, предложение банка (сумму, срок, ставку) или причину отказа от сотрудника; принимает предложение.

Сотрудник банка:
- видит общую очередь и «Мои разборы», берёт заявку в работу;
- запускает скоринг (`scoring/main`, CatBoost) и видит годовую PD, лимит PD и рассчитанное предложение;
- фиксирует проверку сведений с указанием источника;
- принимает решение: одобрить рассчитанное предложение, отказать или запросить данные. Решение всегда сопровождается причиной.

Система сохраняет все изменения в PostgreSQL, проверяет роль и владельца заявки, версию и повтор запроса (`request_id`), ведёт журнал событий и снимает предложение, если исходные данные изменились до его принятия.

Сценарий завершается принятием предложения клиентом. Подписание документов и выдача средств в текущей версии не реализованы.

## Схема

```mermaid
flowchart LR
    B[Браузер: кабинет клиента и сотрудника] -->|HTTP /api/v2, cookie| S[cabinet_server<br/>personalCab/prom_v2]
    S -->|статика| W[personalCab/web/dist]
    S --> P[(PostgreSQL 17<br/>business_scoring:<br/>public v3 + aurelius_cabinet)]
    S -->|библиотека| M[scoring/main<br/>CatBoost, политика, предложение]
    M --> P
    S -->|ассистент| O[Ollama<br/>gpt-oss:20b]
    S --> R[RAG по knowledge/]
```

Подробная архитектура — в [docs/05-architecture.md](docs/05-architecture.md).

## Запуск за 5 минут

Нужны Git и Docker Engine с Compose v2 (или Docker Desktop в режиме Linux-контейнеров). Python и Node на хосте не нужны. Для `gpt-oss:20b` нужно около 16 ГБ свободной RAM и около 14 ГБ на диске. Первый запуск дольше пяти минут: скачивается модель.

Linux / macOS:

```sh
git clone -b test-dev https://github.com/CyberGeo335/AURELIUS.git
cd AURELIUS
cp .env.example .env
# Откройте .env и задайте непустой POSTGRES_PASSWORD.
sh start.sh
```

Windows PowerShell:

```powershell
git clone -b test-dev https://github.com/CyberGeo335/AURELIUS.git
cd AURELIUS
Copy-Item .env.example .env
# Откройте .env и задайте непустой POSTGRES_PASSWORD.
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

После готовности модели откройте http://127.0.0.1:5173.

Скрипт сначала проверяет внешний Ollama (`OLLAMA_BASE_URL`). Если тот недоступен, скрипт поднимает Ollama в Docker, скачивает модель и ждёт успешной проверки генерации. При первом запуске в пустой том восстанавливается синтетическая БД `scoring/bd/v_3 (actual)/business_scoring_wauth.backup`.

Статус и логи:

```sh
docker compose ps -a
docker compose logs -f model-init app
```

Переменные окружения, порты, остановка, сброс, GPU и частые ошибки описаны в [docs/09-deployment.md](docs/09-deployment.md).

## Тестовые учётные записи

В БД 32 синтетические учётные записи: 30 клиентов, каждый привязан к своей компании, и 2 сотрудника банка (`scoring/bd/seeds/seed_user_accounts.py`). Логины и пароли берутся из запущенной БД (вывод содержит пароли открытым текстом):

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT login, password, role, company_id FROM public.user_accounts ORDER BY role, login"'
```

`role=CLIENT` — клиент, `role=BANK_EMPLOYEE` — сотрудник банка. Пароли хранятся как есть; это допущение демо.

Заявки из дампа отменены. Новые заявки создаются в ходе сценария.

## Сценарий проверки

> TODO: короткий сценарий из 5–7 шагов появится после проверки на стенде (этап 4). Подробные пути будут в [docs/03-demo-scenarios.md](docs/03-demo-scenarios.md).

## Документация

| Файл | Что внутри |
|---|---|
| [docs/00-jury-guide.md](docs/00-jury-guide.md) | путеводитель и карта соответствия требованиям кейса |
| [docs/01-problem-and-scope.md](docs/01-problem-and-scope.md) | проблема, решение, границы MVP |
| [docs/02-decisions.md](docs/02-decisions.md) | ключевые решения, ограничения, развитие |
| [docs/03-demo-scenarios.md](docs/03-demo-scenarios.md) | демо-пути со скриншотами |
| [docs/04-credit-process.md](docs/04-credit-process.md) | кредитный процесс, диаграмма состояний заявки, скоринг ≠ решение |
| [docs/05-architecture.md](docs/05-architecture.md) | архитектура и enterprise-аспекты |
| [docs/06-api.md](docs/06-api.md), [docs/api/openapi.yaml](docs/api/openapi.yaml), [docs/api/aurelius.postman_collection.json](docs/api/aurelius.postman_collection.json) | API, OpenAPI и коллекция запросов |
| [docs/07-data-model.md](docs/07-data-model.md) | модель данных, синтетические данные, учётки |
| [docs/08-testing.md](docs/08-testing.md) | тестовые сценарии и результаты прогонов |
| [docs/09-deployment.md](docs/09-deployment.md) | окружение, запуск, переменные, проблемы |
| [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) | сторонние компоненты, модели, датасеты, смоделированные интеграции |

> TODO: файлы `00`–`08` и `docs/api/` пишутся на следующих этапах. До их появления ссылки не работают.

## Используемые компоненты

- Фронт: React 19, TypeScript, Vite, Tailwind CSS, Radix UI, Motion; шрифты Onest и Unbounded (`personalCab/web/package.json`, `package-lock.json`).
- Backend: Python 3.13, стандартный `http.server`, psycopg 3 (`personalCab/prom_v2/cabinet_server.py`, `requirements.txt`).
- БД: PostgreSQL 17.
- Скоринг: CatBoost, собственная модель `dt_monotone_v1`, обученная на синтетике (`scoring/main`).
- Ассистент: LangGraph, LangChain, Ollama, `gpt-oss:20b` (открытые веса); RAG на FAISS по `knowledge/`.

Версии зафиксированы в `requirements.lock.txt` и `personalCab/web/package-lock.json`, образ Ollama — по digest в `compose.yaml`. Полный перечень с лицензиями — в [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Ограничения демо

- Данные синтетические. Внешние источники (БКИ, ЕГРЮЛ/ЕГРИП, ФНС, Реестр МСП, банковская выписка) смоделированы данными в БД.
- Подписание документов и выдача средств не реализованы.
- Пароли хранятся открытым текстом, HTTPS не настроен.
- Внутренние причины скоринга скрывает от клиента интерфейс; ответ API клиенту их пока содержит.
- LLM только с открытыми весами (`gpt-oss:20b`), запускается локально. Платные сервисы не используются.

## Что не входит в текущую версию

В репозитории остались материалы прежних этапов. Они не запускаются и не описывают текущее поведение:

- `personalCab/frontend/` — первый кабинет на HTML/JS со своим Python-сервером;
- `personalCab/prom_v2/web_server.py` и БД `aurelius_v2` — предыдущий сервер V2;
- mock-режим фронта (сборка без `VITE_API_MODE=http`) с локальными демо-учётками и симуляцией подписи и выдачи;
- `docs/V2_*.md`, `docs/DEMO_MODULES_1_5.md`, `AGENTS.md`, `DataAndArcBuild/architecture/`, `DataAndArcBuild/architecture_v2/` — описания прежних этапов.

Код из `personalCab/prom/` частично используется текущим ассистентом: RAG `personalCab/prom/rag` и схема извлечения из `personalCab/prom/prom_lab/ai_agents_lab/agents/factory.py`.

## Версия

Документация проверена на коммите `40b8038` ветки `test-dev`. Версия для жюри фиксируется тегом или commit hash на момент дедлайна.

> TODO: указать итоговый тег или commit hash.
