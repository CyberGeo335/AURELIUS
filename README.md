# AURELIUS — умный кредитный кабинет

Текущий запуск: кабинет v3, PostgreSQL 17, `scoring/main`, Agent V2 и Ollama.
Это DEMO на синтетических данных. Финансовая модель и политика при Docker-запуске не меняются.

## Быстрый старт

Нужны Git, Docker Engine с Compose v2 (или Docker Desktop в режиме Linux containers).
Для `gpt-oss:20b` предусмотрите примерно 16 ГБ доступной RAM и 14 ГБ под модель,
а также дополнительное место под образы и БД. CPU поддерживается; первый ответ может быть долгим.
На Linux нужен Docker с поддержкой `host-gateway`. Python и Node на хосте не нужны.

Из корня клонированного репозитория, Linux/macOS:

```sh
cp .env.example .env
# Откройте .env и задайте POSTGRES_PASSWORD.
sh start.sh
```

Windows PowerShell:

```powershell
Copy-Item .env.example .env
# Откройте .env и задайте POSTGRES_PASSWORD.
powershell -NoProfile -ExecutionPolicy Bypass -File .\start.ps1
```

После готовности модели кабинет доступен по http://127.0.0.1:5173.
Скрипт собирает фронт в HTTP-режиме, проверяет внешний Ollama из Docker.
Если внешний Ollama недоступен, запускает `ollama/ollama` в Docker и использует его.
На хост Ollama не устанавливается. Linux получает `host.docker.internal:host-gateway`.
При доступном Ollama существующая модель используется без повторной загрузки.
Отсутствующая модель скачивается автоматически; прогресс виден в выводе запуска и логах.
Кабинет ждёт завершения скачивания и успешной проверки инференса.

```sh
docker compose logs -f model-init app
docker compose ps -a
```

При ошибке запуска скрипт останавливается: проверки не отключаются.
`docker compose up -d` подходит, когда внешний Ollama уже доступен по адресу из `.env`;
для автоматического выбора внешнего Ollama или контейнера используйте `start.sh` / `start.ps1`.
Повторять запуск также следует через этот скрипт.

## База данных и вход

В пустой том автоматически восстанавливается `scoring/bd/v_3 (actual)/business_scoring_wauth.backup`.
Проверяются 30 компаний, 30 заявок, 32 учётные записи, 3 набора параметров политики и 1 макропоказатель.
Проверка фиксируется в отдельной `aurelius_deploy`, не меняя схему `public`.
После первого запуска заявки могут добавляться: повторный старт не требует ровно 30 заявок.
`init` применяет только миграции кабинета 005–009. Документы и диалоги хранятся в PostgreSQL.
Том БД сохраняется при остановке; модели встроенного Ollama — в отдельном томе.

Просмотр синтетических логинов и открытых паролей (вывод содержит пароли):

```sh
docker compose exec db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT login, password FROM public.user_accounts ORDER BY login"'
```

Та же команда работает в PowerShell. Роли клиент/сотрудник определяются самой БД.
Не публикуйте вывод и не сохраняйте `generated_credentials.csv` в Git.

## Настройки

Все пользовательские настройки — в корневом `.env`; пароля по умолчанию нет.
Не используйте пробел вместо пароля. Значения с `$`/`#` заключайте в одинарные кавычки.
`DATABASE_URL` и совместимый `AURELIUS_DATABASE_URL` создаются entrypoint из одного набора `PG_*`;
пароль и имя пользователя кодируются для URL автоматически. Не нужно вручную кодировать пароль.
В Docker БД всегда `db:5432`; `POSTGRES_PORT` — только порт доступа с хоста.
Фронт требует `VITE_API_MODE=http`; после изменения build-настроек требуется пересборка.
Модель и её `features.json`/`best_config.json` копируются из `scoring/main/ml_scoring/model`.
Старая схема `aurelius_v2`, старый web_server и frontend/server в запуск не входят.
`compose.v2.yaml` — альтернативное имя того же актуального Compose, без отдельной БД.
`Dockerfile.v2` и `personalCab/web/Dockerfile` также собирают актуальный кабинет:
контекст сборки — корень репозитория, target `runtime`.

Для NVIDIA установите NVIDIA Container Toolkit и подключите override перед запуском:

```sh
COMPOSE_FILE=compose.yaml:compose.gpu.yaml sh start.sh
```

```powershell
$env:COMPOSE_FILE = 'compose.yaml;compose.gpu.yaml'
.\start.ps1
```

Override влияет только на встроенный Ollama. По умолчанию используется CPU.

## Остановка, обновление и сброс

Остановка без удаления данных:

```sh
docker compose --profile bundled down
```

Обновление:

```sh
git pull --ff-only
sh start.sh
```

В Windows после `git pull --ff-only` выполните `start.ps1`.
Обновление не восстанавливает дамп поверх существующего тома и не скачивает установленную модель снова.

**Полный сброс удаляет БД, документы, диалоги и модели встроенного Ollama:**

```sh
docker compose --profile bundled down -v
```

Чтобы сбросить только БД, сначала выполните `down`, затем удалите только том
`<COMPOSE_PROJECT_NAME>_postgres_data` через `docker volume rm`.
Следующий запуск восстановит исходный дамп. Не применяйте сброс к нужным данным.
Если подключён том от прежнего запуска без `aurelius_deploy`, init остановится:
используйте новое `COMPOSE_PROJECT_NAME` для новой установки; существующую БД не перезаписывайте.

## Сервер и частые ошибки

Для публикации на сервере задайте `APP_BIND_HOST=0.0.0.0`, откройте `APP_PORT` в firewall.
Для внешнего использования нужен HTTPS-прокси. Он здесь не настроен;
текущий backend проверяет HTTP Origin, поэтому для HTTPS нужна отдельная настройка приложения.
PostgreSQL публикуется только на loopback, Ollama-контейнер не публикует порт наружу.

- Порт занят: измените `APP_PORT` / `POSTGRES_PORT` в `.env` и повторите скрипт.
- Ollama недоступен: проверьте `OLLAMA_BASE_URL`, доступность из Docker и `docker compose logs model-init`.
  Внешняя Ollama, слушающая только loopback, может быть недоступна контейнерам — тогда скрипт выберет встроенную.
- Модель не помещается в RAM: увеличьте память Docker Desktop / сервера. Кабинет не запустится до готовности модели.
- Нет места: освободите диск; повторите скрипт. Том моделей сохраняет скачанные данные.
- Ошибка пароля / `.env`: задайте непустой `POSTGRES_PASSWORD`; смена переменной не меняет пароль уже созданной БД.
- Ошибка восстановления: смотрите `docker compose logs db`; не восстанавливайте дамп поверх существующей БД.

## Проверки

Python 3.13, точные runtime-зависимости в `requirements.txt`; pytest отдельно в `requirements-dev.txt`.
Исследовательское окружение `scoring/requirements.txt` в образ не устанавливается.

```sh
docker compose --profile tools build tests
docker compose --profile tools run --rm --no-deps tests
# Фронт: из корня репозитория собрать стадию web и запустить тесты.
docker build --target web -t aurelius-web-test .
docker run --rm aurelius-web-test npm test
```

Интеграционные тесты требуют отдельную seeded БД с именем `aurelius_test*` и
`AURELIUS_TEST_DATABASE_URL`. Не направляйте их в рабочую БД. Без неё тесты PostgreSQL пропускаются.
Подробности API и ограничений: [docs/CABINET_V3.md](docs/CABINET_V3.md).
