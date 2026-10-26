# 09. Развёртывание и запуск

Проверено по коду коммита `6a9a4c1` (ветка `chore/cleanup-legacy`).

Документ описывает только текущую версию: кабинет v3, то есть `personalCab.prom_v2.cabinet_server` + фронт `personalCab/web` в HTTP-режиме + PostgreSQL `business_scoring` (дамп v4) + `scoring/main` + ассистент через Ollama.

## 1. Требования к окружению

| Что | Требование | Откуда |
|---|---|---|
| Docker | Docker Engine с Compose v2 или Docker Desktop в режиме Linux-контейнеров | `compose.yaml`, `start.sh`, `start.ps1` |
| ОС | Linux, macOS, Windows (через Docker Desktop) | `start.sh`, `start.ps1` |
| Python, Node, PostgreSQL, Ollama на хосте | не нужны: всё собирается и работает в контейнерах | `Dockerfile` |
| RAM | около 16 ГБ свободной памяти для `gpt-oss:20b` | README |
| Диск | около 25 ГБ при встроенном Ollama: модель 13,8 ГБ, образ Ollama 8,4 ГБ, образ кабинета 1,5 ГБ, образ БД 0,6 ГБ, том БД около 70 МБ. Плюс кэш сборки | ориентир для первого запуска; точный объём зависит от кэша и образов |
| GPU | не обязателен. NVIDIA можно подключить через `compose.gpu.yaml` и NVIDIA Container Toolkit | `compose.gpu.yaml` |
| Linux | Docker с поддержкой `host-gateway` | `compose.yaml` (`extra_hosts`) |
| Сеть | при первом запуске: загрузка образов, пакетов pip и npm и модели (около 14 ГБ) | `Dockerfile`, `deploy/ollama_ready.py` |

На CPU модель работает, но первый ответ ассистента может идти долго. Таймаут одного обращения к модели в кабинете — 120 секунд (`personalCab/prom_v2/adapters.py`).

## 2. Сервисы и порты

| Сервис | Образ / команда | Что делает | Порт на хосте |
|---|---|---|---|
| `db` | `postgres:17` + `deploy/00_restore.sh` | PostgreSQL 17. В пустой том один раз восстанавливает `scoring/bd/v_4 (actual)/business_scoring_wauth.backup` и создаёт отметку `aurelius_deploy.seed_validation` | `127.0.0.1:${POSTGRES_PORT:-5433}` → 5432 |
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

Откройте Docker Desktop, включите Linux containers / WSL 2 и дождитесь готовности
Engine. Команды `docker info` и `docker compose version` должны завершаться
без ошибки. В существующем клоне сначала выполните `git switch main` и
`git pull --ff-only origin main`. Существующий `.env` не перезаписывайте.

```powershell
Copy-Item .env.example .env
# Откройте .env и задайте непустой POSTGRES_PASSWORD.
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

Что делает скрипт (`start.sh` / `start.ps1`):

1. Останавливается, если нет `.env`. PowerShell также сначала проверяет доступность Docker Engine и Compose v2.
2. Собирает образы `app` и `db` (`docker compose build app db`). Фронт собирается внутри образа с `VITE_API_MODE=http`.
3. Запускает `probe`: проверяет из контейнера внешний Ollama по `OLLAMA_BASE_URL`. Если тот недоступен (код 2), задаёт временный `OLLAMA_ENDPOINT=http://ollama:11434` и поднимает встроенный `ollama`.
4. Поднимает `db`, `init`, `model-init` и показывает лог `model-init`: прогресс загрузки модели и проверку генерации.
5. Если `model-init` завершился не с кодом 0, останавливается с ошибкой. Проверки при этом не отключаются.
6. Запускает `app` (`docker compose up -d --no-deps app`). PowerShell ждёт состояния `healthy` до 120 секунд и только затем сообщает об успехе. При `unhealthy` или остановке контейнера сообщает об ошибке.

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

Тестовые учётные записи (логин и пароль) берутся из БД. Роль (клиент или сотрудник банка) и компания определяются самой БД. Все учётки синтетические.

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

## 8. Адрес демонстрации

Стандартный локальный адрес — `http://127.0.0.1:<APP_PORT>`. Для доступа к локальной установке через уже настроенный SSH-сервер можно пробросить порт:

```sh
ssh -N -L 55173:127.0.0.1:5173 <пользователь>@<сервер>
```

На компьютере проверяющего откройте `http://127.0.0.1:55173`. В примере `5173` — APP_PORT на машине запуска. PostgreSQL публикуется только на loopback; контейнер Ollama порт наружу не публикует.

## 9. Автотесты в Docker

Python-тесты (`scoring/main/tests`, `personalCab/prom_v2/tests`, `deploy/tests`, `personalCab/prom/prom_lab/ai_agents_lab/tests`):

```sh
docker compose --profile tools build tests
docker compose --profile tools run --rm --no-deps tests
```

Фронт:

```sh
docker build --target web -t aurelius-web-test .
docker run --rm aurelius-web-test npm test
```

Интеграционным тестам PostgreSQL нужна отдельная БД с данными, имя которой начинается с `aurelius_test`, и переменная `AURELIUS_TEST_DATABASE_URL`. Без неё эти тесты пропускаются. Рабочую БД для тестов не используйте. Фактические результаты прогонов — в [08-testing.md](08-testing.md).

## 10. Частые проблемы

| Симптом | Причина и что сделать |
|---|---|
| Docker не найден / Engine недоступен | установите или запустите Docker Desktop в режиме Linux containers / WSL 2, дождитесь готовности Engine; проверьте `docker info` и `docker compose version` |
| `set: -\r: invalid option` в старом Windows-запуске | обновите `main` и повторите `start.ps1`: скрипт пересоберёт образ БД; `.gitattributes` и Dockerfile защищают shell-скрипт от CRLF |
| `Задайте непустой POSTGRES_PASSWORD в .env` или `PG_PASSWORD must be nonempty` | в `.env` пустой пароль. Задайте непустой; пробел не подходит |
| Порт занят | измените `APP_PORT` или `POSTGRES_PORT` в `.env` и повторите скрипт |
| `External Ollama unavailable; use bundled Docker service.` | это не ошибка: скрипт переходит на встроенный Ollama. Внешний Ollama, слушающий только loopback хоста, контейнерам недоступен |
| `model-init` долго качает модель | первый запуск: около 14 ГБ. Прогресс — в `docker compose logs -f model-init`. Скачанное остаётся в томе `ollama_models` |
| `Модель не готова (...)` | не хватает памяти или сбой Ollama. Увеличьте память Docker Desktop или сервера и смотрите `docker compose logs model-init`. Кабинет не стартует, пока модель не готова |
| Нет места на диске | освободите место и повторите скрипт; уже скачанные части модели сохраняются |
| `init` падает с `Seed validation failed` | дамп восстановлен не полностью или том не пустой. Смотрите `docker compose logs db` и не восстанавливайте дамп поверх существующей БД |
| `init` падает на `aurelius_deploy` | подключён том от прежней установки. Задайте новое `COMPOSE_PROJECT_NAME` |
| Ассистент отвечает ошибкой 503 | модель не ответила (таймаут 120 секунд). Выдуманный ответ не подставляется; повторите сообщение |

После прежней ошибки CRLF том может быть частично инициализирован. Если `init`
сообщает об отсутствии `aurelius_deploy`, остановите прежний проект командой
`docker compose --profile bundled down` (без `-v`), задайте новое уникальное
`COMPOSE_PROJECT_NAME` в `.env` и повторите запуск. Старый том сохранится;
не удаляйте его, если там могут быть нужные данные. Глобально отключать
`core.autocrlf` не нужно: `*.sh` выгружаются с LF, а образ PostgreSQL дополнительно
нормализует окончания строк при сборке.

## 11. Существующая установка и дамп v4

Новый пустой том получает v4 автоматически. Смена backup в Compose не изменяет уже существующий том. Для существующего DEMO-контура предусмотрено явное добавочное обновление выручки:

```sh
docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < scoring/bd/seeds/backfill_revenue_2025_09_10.sql
```

Команда выше — для POSIX shell. В PowerShell передайте SQL через stdin:

```powershell
Get-Content -Raw 'scoring/bd/seeds/backfill_revenue_2025_09_10.sql' | docker compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Скрипт рассчитан на 30 эталонных DEMO-компаний, проверяет их состав и работает в транзакции. Полный backup используется только для новой пустой БД. Формат и проверка эталона — [README v4](../scoring/bd/v_4%20(actual)/README.md).

## 12. Состав проверки запуска

Готовность сервисов проверяется healthcheck БД, завершением `init` и `model-init`, ответом приложения и доступностью сессии. Автотесты скриптов запуска входят в `deploy/tests/test_launch.py`. Протоколы прикладных запусков и их объём — [08](08-testing.md#2-протоколы-проверок).
