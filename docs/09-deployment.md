# 09. Развёртывание и запуск

Проверено на коммите `40b8038` (ветка `test-dev`).

Документ описывает только текущую версию: кабинет v3, то есть `personalCab.prom_v2.cabinet_server` + фронт `personalCab/web` в HTTP-режиме + PostgreSQL `business_scoring` v3 + `scoring/main` + ассистент через Ollama. Старые `personalCab/frontend/server.py`, `prom_v2.web_server` и БД `aurelius_v2` в запуск не входят.

## 1. Требования к окружению

| Что | Требование | Откуда |
|---|---|---|
| Docker | Docker Engine с Compose v2 или Docker Desktop в режиме Linux-контейнеров | `compose.yaml`, `start.sh`, `start.ps1` |
| ОС | Linux, macOS, Windows (через Docker Desktop) | `start.sh`, `start.ps1` |
| Python, Node, PostgreSQL, Ollama на хосте | не нужны: всё собирается и работает в контейнерах | `Dockerfile` |
| RAM | около 16 ГБ свободной памяти для `gpt-oss:20b` | README |
| Диск | около 25 ГБ при встроенном Ollama: модель 13,8 ГБ, образ Ollama 8,4 ГБ, образ кабинета 1,5 ГБ, образ БД 0,6 ГБ, том БД около 70 МБ. Плюс кэш сборки (около 2,8 ГБ на проверочном ПК) | `docker system df -v`, раздел 12 |
| GPU | не обязателен. NVIDIA можно подключить через `compose.gpu.yaml` и NVIDIA Container Toolkit | `compose.gpu.yaml` |
| Linux | Docker с поддержкой `host-gateway` | `compose.yaml` (`extra_hosts`) |
| Сеть | при первом запуске: загрузка образов, пакетов pip и npm и модели (около 14 ГБ) | `Dockerfile`, `deploy/ollama_ready.py` |

На CPU модель работает, но первый ответ ассистента может идти долго. Таймаут одного обращения к модели в кабинете — 120 секунд (`personalCab/prom_v2/adapters.py`).

## 2. Сервисы и порты

| Сервис | Образ / команда | Что делает | Порт на хосте |
|---|---|---|---|
| `db` | `postgres:17` + `deploy/00_restore.sh` | PostgreSQL 17. В пустой том один раз восстанавливает `scoring/bd/v_3 (actual)/business_scoring_wauth.backup` и создаёт отметку `aurelius_deploy.seed_validation` | `127.0.0.1:${POSTGRES_PORT:-5433}` → 5432 |
| `init` | `python /app/deploy/initialize.py` | при первом запуске сверяет число строк дампа (30 компаний, 30 заявок, 32 учётные записи, 3 строки политики, 1 макропоказатель), затем применяет миграции кабинета 005–009 | нет |
| `ollama` | `ollama/ollama@sha256:dea72d1e…` | встроенный Ollama. Запускается только если внешний недоступен (профиль `bundled`) | не публикуется |
| `model-init` | `python /app/deploy/ollama_ready.py` | ждёт Ollama, скачивает модель, если её нет, и проверяет генерацию | нет |
| `app` | `python -m personalCab.prom_v2.cabinet_server --host 0.0.0.0 --port 5173` | кабинет: статика фронта и API `/api/v2`. Стартует только после успешных `init` и `model-init` | `${APP_BIND_HOST:-127.0.0.1}:${APP_PORT:-5173}` → 5173 |
| `probe` | `ollama_ready.py --probe` (профиль `tools`) | проверяет из Docker, доступен ли внешний Ollama. Код 0 — доступен, 2 — нет | нет |
| `tests` | образ `test` (профиль `tools`) | автотесты Python | нет |

Тома: `postgres_data` (БД, документы и диалоги хранятся в PostgreSQL) и `ollama_models` (модели встроенного Ollama). Имена томов начинаются с `COMPOSE_PROJECT_NAME`.

## 3. Запуск

Из корня клонированного репозитория.

Linux / macOS:

```sh
cp .env.example .env
# Откройте .env и задайте непустой POSTGRES_PASSWORD.
sh start.sh
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
# Откройте .env и задайте непустой POSTGRES_PASSWORD.
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Что делает скрипт (`start.sh` / `start.ps1`):

1. Останавливается, если нет `.env`.
2. Собирает образ `app` (`docker compose build app`). Фронт собирается внутри образа с `VITE_API_MODE=http`.
3. Запускает `probe`: проверяет из контейнера внешний Ollama по `OLLAMA_BASE_URL`. Если тот недоступен (код 2), задаёт временный `OLLAMA_ENDPOINT=http://ollama:11434` и поднимает встроенный `ollama`.
4. Поднимает `db`, `init`, `model-init` и показывает лог `model-init`: прогресс загрузки модели и проверку генерации.
5. Если `model-init` завершился не с кодом 0, останавливается с ошибкой. Проверки при этом не отключаются.
6. Запускает `app` (`docker compose up -d --no-deps app`).

После этого кабинет открывается по адресу `http://127.0.0.1:5173` (или по вашему `APP_PORT`).

`docker compose up -d` без скрипта подходит, только если внешний Ollama уже доступен по адресу из `.env`. Выбирать между внешним и встроенным Ollama умеет только скрипт, поэтому повторный запуск тоже делайте через него.

Для NVIDIA:

```sh
COMPOSE_FILE=compose.yaml:compose.gpu.yaml sh start.sh
```

```powershell
$env:COMPOSE_FILE = 'compose.yaml;compose.gpu.yaml'
.\start.ps1
```

Override действует только на встроенный Ollama. По умолчанию используется CPU.

## 4. Переменные окружения

Все пользовательские настройки лежат в корневом `.env`, шаблон — `.env.example`. Файл `.env` исключён из Git и из Docker-контекста (`.gitignore`, `.dockerignore`).

| Переменная | По умолчанию | Обязательна | Назначение |
|---|---|---|---|
| `POSTGRES_PASSWORD` | нет (пусто в шаблоне) | да | пароль PostgreSQL. Compose не стартует без него, `deploy/runtime.py` отклоняет пустой. Значения с `$` или `#` берите в одинарные кавычки |
| `POSTGRES_USER` | `aurelius` | да | пользователь PostgreSQL |
| `POSTGRES_DB` | `business_scoring` | да | имя БД |
| `POSTGRES_PORT` | `5433` | нет | порт PostgreSQL на хосте (только loopback). Внутри Docker всегда `db:5432` |
| `APP_BIND_HOST` | `127.0.0.1` | нет | адрес публикации кабинета. `0.0.0.0` открывает доступ с других компьютеров |
| `APP_PORT` | `5173` | нет | порт кабинета на хосте |
| `COMPOSE_PROJECT_NAME` | `aurelius` | нет | имя проекта. Изолирует контейнеры и тома, поэтому для второй установки на том же ПК задайте другое |
| `OLLAMA_BASE_URL` | `http://host.docker.internal:11434` | нет | адрес внешнего Ollama, проверяется первым |
| `OLLAMA_MODEL` | `gpt-oss:20b` | нет | модель ассистента |
| `VITE_API_MODE` | `http` | да | режим сборки фронта. Допустимо только `http`: иначе сборка останавливается (`Dockerfile`). После изменения нужна пересборка |
| `COMPOSE_FILE` | не задана | нет | подключение `compose.gpu.yaml` |

Переменные, которые задаёт Compose или скрипт (вручную их задавать не нужно):

| Переменная | Значение | Где задаётся |
|---|---|---|
| `PG_HOST`, `PG_PORT` | `db`, `5432` | `compose.yaml` |
| `PG_DATABASE`, `PG_USER`, `PG_PASSWORD` | из `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` | `compose.yaml` |
| `DATABASE_URL`, `AURELIUS_DATABASE_URL` | собираются из `PG_*` с URL-кодированием логина, пароля и имени БД | `deploy/runtime.py` (entrypoint образа) |
| `OLLAMA_ENDPOINT` | `http://ollama:11434`, только при переходе на встроенный Ollama | `start.sh`, `start.ps1` |

Необязательные переменные кода:

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `AURELIUS_MODEL_PATH`, `AURELIUS_FEATURES_PATH`, `AURELIUS_MODEL_CONFIG_PATH` | `scoring/main/ml_scoring/model/best_model.cbm`, `features.json`, `best_config.json` | другие файлы скоринговой модели (`scoring/main/config.py`) |
| `AURELIUS_TEST_DATABASE_URL` | не задана | только для интеграционных тестов: отдельная БД с именем `aurelius_test*` |

Если поменять `POSTGRES_PASSWORD` после первого запуска, пароль уже созданной БД не изменится.

## 5. Проверка готовности

```sh
docker compose ps -a
```

Ожидаемое состояние: `db` — `healthy`; `init` и `model-init` — `Exited (0)`; `app` — `healthy`; `ollama` — `Up`, если используется встроенный.

Healthcheck `app` (`deploy/healthcheck.py`) считает кабинет готовым, когда главная страница отдаёт 200 с HTML, а `GET /api/v2/session` без входа отдаёт 401. То же можно проверить вручную:

```sh
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/              # 200
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:5173/api/v2/session  # 401
```

Лог `init` при первом запуске:

```text
companies: 30 (expected 30)
credit_applications: 30 (expected 30)
user_accounts: 32 (expected 32)
risk_policy_parameters: 3 (expected 3)
macro_indicators: 1 (expected 1)
Cabinet migrations 005–009 completed.
```

При повторных запусках вместо сверки выводится `Initial seed already validated; existing business data preserved.`: заявки, созданные в кабинете, сохраняются.

Тестовые учётные записи (логин и пароль) берутся из БД. Роль (клиент или сотрудник банка) и компания определяются самой БД. Вывод содержит пароли открытым текстом; все учётки синтетические.

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT login, password, role, company_id FROM public.user_accounts ORDER BY role, login"'
```

На проверочном стенде: 30 учёток `CLIENT` (по одной на каждую из 30 компаний: 26 юрлиц и 4 ИП) и 2 учётки `BANK_EMPLOYEE`, все активны.

## 6. Логи

```sh
docker compose logs -f model-init app   # загрузка модели и кабинет
docker compose logs init                # сверка дампа и миграции
docker compose logs db                  # восстановление дампа
docker compose --profile bundled logs ollama
```

Сервер кабинета не пишет в лог тела запросов, пароли, cookie и параметры запросов (`cabinet_server.py`, `log_message`).

## 7. Остановка, обновление, сброс

Остановка без удаления данных:

```sh
docker compose --profile bundled down
```

Обновление до новой версии:

```sh
git pull --ff-only
sh start.sh            # Windows: .\start.ps1
```

Обновление не восстанавливает дамп поверх существующего тома и не скачивает уже установленную модель заново.

Полный сброс удаляет БД, документы, диалоги и модели встроенного Ollama:

```sh
docker compose --profile bundled down -v
```

Чтобы сбросить только БД, сначала выполните `down`, затем удалите том `<COMPOSE_PROJECT_NAME>_postgres_data` командой `docker volume rm`. Следующий запуск восстановит исходный дамп.

Если подключить том от прежнего запуска без схемы `aurelius_deploy`, `init` остановится. Для новой установки задайте другое `COMPOSE_PROJECT_NAME`, а существующую БД не перезаписывайте.

## 8. Доступ с других компьютеров

- Задайте `APP_BIND_HOST=0.0.0.0` и откройте `APP_PORT` в firewall.
- HTTPS не настроен. Сервер принимает POST, только если заголовок `Origin` равен `http://<Host>` (`cabinet_server.py`, `do_POST`). За HTTPS-прокси без отдельной настройки приложения вход и действия будут отклоняться с 403.
- PostgreSQL публикуется только на loopback, контейнер Ollama порт наружу не публикует.

## 9. Автотесты в Docker

Python-тесты (`scoring/main/tests`, `personalCab/prom_v2/tests`, `deploy/tests`):

```sh
docker compose --profile tools build tests
docker compose --profile tools run --rm --no-deps tests
```

Фронт:

```sh
docker build --target web -t aurelius-web-test .
docker run --rm aurelius-web-test npm test
```

Интеграционным тестам PostgreSQL нужна отдельная БД с данными, имя которой начинается с `aurelius_test`, и переменная `AURELIUS_TEST_DATABASE_URL`. Без неё эти тесты пропускаются. Рабочую БД для тестов не используйте. Фактические результаты прогонов будут в [08-testing.md](08-testing.md).

## 10. Частые проблемы

| Симптом | Причина и что сделать |
|---|---|
| `Задайте непустой POSTGRES_PASSWORD в .env` или `PG_PASSWORD must be nonempty` | в `.env` пустой пароль. Задайте непустой; пробел не подходит |
| Порт занят | измените `APP_PORT` или `POSTGRES_PORT` в `.env` и повторите скрипт |
| `External Ollama unavailable; use bundled Docker service.` | это не ошибка: скрипт переходит на встроенный Ollama. Внешний Ollama, слушающий только loopback хоста, контейнерам недоступен |
| `model-init` долго качает модель | первый запуск: около 14 ГБ. Прогресс — в `docker compose logs -f model-init`. Скачанное остаётся в томе `ollama_models` |
| `Модель не готова (...)` | не хватает памяти или сбой Ollama. Увеличьте память Docker Desktop или сервера и смотрите `docker compose logs model-init`. Кабинет не стартует, пока модель не готова |
| Нет места на диске | освободите место и повторите скрипт; уже скачанные части модели сохраняются |
| `init` падает с `Seed validation failed` | дамп восстановлен не полностью или том не пустой. Смотрите `docker compose logs db` и не восстанавливайте дамп поверх существующей БД |
| `init` падает на `aurelius_deploy` | подключён том от прежней установки. Задайте новое `COMPOSE_PROJECT_NAME` |
| Вход и действия возвращают 403 «Недопустимый источник запроса» | кабинет открыт через прокси или по адресу, где `Origin` не совпадает с `Host`. Открывайте напрямую `http://<хост>:<APP_PORT>` |
| Ассистент отвечает ошибкой 503 | модель не ответила (таймаут 120 секунд). Выдуманный ответ не подставляется; повторите сообщение |

## 11. Ограничения запуска

- HTTPS, хэширование паролей и production-аутентификация не настроены. Это демо на синтетических данных.
- Экономическая политика `AURELIUS_MVP_20261024_V1` в `risk_policy_parameters` действует с 24.10.2026 по 17.12.2026 (проверено запросом к БД стенда; см. также `scoring/main/decision_engine/BASELINE.md`). Скоринг выбирает политику на текущую дату (`scoring/main/database.py`, `load_snapshot`). После 17.12.2026 запись не найдётся. Как поведёт себя расчёт в этом случае, не проверялось.
- Финансовая история в дампе — 12 месяцев выручки на компанию (с 15.11.2025 по 15.10.2026, `bank_transactions`). Автоматическому расчёту PD нужно 13 завершённых месяцев (`scoring/main/ml_scoring/feature_builder.py`). Поэтому на исходных данных скоринг возвращает ручную проверку без PD. Подробнее — в [04-credit-process.md](04-credit-process.md) и [03-demo-scenarios.md](03-demo-scenarios.md).
- Ручной запуск без Docker (для разработки) описан в [CABINET_V3.md](CABINET_V3.md) и в эту инструкцию не входит.

## 12. Результаты проверки запуска

Запуск 26.10.2026 на коммите `40b8038`: чистый `git clone -b test-dev`, `.env` из `.env.example` с изменёнными `POSTGRES_PASSWORD`, `COMPOSE_PROJECT_NAME=aurelius-docs`, `APP_PORT=55173`, `POSTGRES_PORT=55433`. Репозиторий не менялся, `git status` чистый.

| Параметр | Значение |
|---|---|
| ОС и Docker | Windows, Docker Desktop (Linux containers), Docker 29.8.1, Compose v5.5.1; Docker выделено 16 CPU и 16,7 ГБ памяти |
| Скрипт | `start.ps1` через PowerShell |
| Ollama | внешний недоступен (`External Ollama unavailable; use bundled Docker service.`), использован встроенный |
| Модель | `gpt-oss:20b` скачана с нуля в новый том (основной слой 13 793 422 816 байт), проверка генерации прошла |
| Время | от запуска `start.ps1` (07:26:10) до старта `app` (07:32:06) — около 6 минут, из них большая часть — загрузка модели. Образ кабинета собран из кэша сборки этого ПК |
| `docker compose ps -a` | `db` healthy, `init` Exited (0), `model-init` Exited (0), `app` healthy, `ollama` Up |
| Лог `init` | 30 компаний, 30 заявок, 32 учётки, 3 строки политики, 1 макропоказатель; `Cabinet migrations 005–009 completed.` |
| Healthcheck с хоста | `GET /` — 200, `GET /api/v2/session` — 401 |
| БД | PostgreSQL 17.11; 35 таблиц в `public`; 10 таблиц в `aurelius_cabinet`; все 30 заявок дампа — `CANCELLED` |
| Вход через API | клиент и сотрудник: `POST /api/v2/login` — 200, cookie `HttpOnly; SameSite=Strict; Path=/api/v2; Max-Age=28800`; `GET /api/v2/state` у клиента — 1 компания, 1 заявка, у сотрудника — 30 компаний, 30 заявок; после `logout` сессия — 401; неверный пароль — 401; чужой `Origin` — 403 |
| Размеры | образ кабинета 1,54 ГБ, образ БД 640 МБ, образ Ollama 8,43 ГБ, том модели 13,79 ГБ, том БД 69 МБ |

Первая попытка за минуту до этого, сразу после запуска Docker Desktop, завершилась кодом 1 без сохранённого вывода. Вторая, без изменений, прошла полностью. Причину установить не удалось.

Не проверено в этом прогоне: Linux, NVIDIA (`compose.gpu.yaml`), загрузка образов без кэша сборки, `start.sh` на Windows. Предыдущая проверка на macOS (Linux ARM64 containers) — в [DOCKER_VALIDATION.md](DOCKER_VALIDATION.md), на коммите `d54cb92`.
