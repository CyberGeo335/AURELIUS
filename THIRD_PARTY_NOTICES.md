# THIRD_PARTY_NOTICES

Перечень сторонних компонентов, моделей, датасетов, сервисов и смоделированных интеграций, которые входят в проверяемую версию AURELIUS.

Проверено на коммите `40b8038` (ветка `test-dev`).

Все компоненты ниже бесплатны и не требуют платных подписок, API или закрытых корпоративных лицензий. Для запуска нужен только Docker, сеть нужна для загрузки образов, пакетов и модели.

## Как собран перечень

| Группа | Откуда список версий | Откуда лицензии |
|---|---|---|
| Python | `requirements.lock.txt` (71 пакет, Python 3.13) | метаданные установленных пакетов, `pip-licenses` |
| Python, только тесты | `requirements-dev.txt` | `pip-licenses` |
| npm | `personalCab/web/package-lock.json` после `npm ci` (330 пакетов) | `license-checker-rseidelsohn --production` и полный прогон |
| Docker-образы | `Dockerfile`, `deploy/Postgres.Dockerfile`, `compose.yaml` | официальные страницы проектов (ссылки ниже) |
| Модель LLM | `OLLAMA_MODEL` в `.env.example` и `compose.yaml` | карточка модели (ссылка ниже) |

Лицензии указаны так, как их объявляют сами пакеты. Где пакет объявляет несколько лицензий, они перечислены через `AND` / `OR`, как в метаданных.

## Сервисы и образы Docker

| Компонент | Версия / ссылка в репозитории | Назначение | Лицензия |
|---|---|---|---|
| PostgreSQL | образ `postgres:17` (`deploy/Postgres.Dockerfile`) | БД `business_scoring` | [PostgreSQL License](https://www.postgresql.org/about/licence/) |
| Ollama | образ `ollama/ollama@sha256:dea72d1e…322d8` (`compose.yaml`, профиль `bundled`) | локальный сервер LLM, если внешний Ollama недоступен | MIT ([Ollama](https://en.wikipedia.org/wiki/Ollama)) |
| Python | образ `python:3.13-slim` (`Dockerfile`, стадии `runtime` и `test`) | среда backend | [PSF License 2.0](https://docs.python.org/3/license.html) |
| Node.js | образ `node:24-alpine` (`Dockerfile`, стадия `web`) | только сборка фронта; в итоговый образ не входит | [MIT-подобная лицензия Node.js](https://github.com/nodejs/node/blob/main/LICENSE) |

Образы содержат пакеты своих дистрибутивов (Debian, Alpine) под их собственными лицензиями. Здесь они отдельно не перечислены.

## Модели

| Модель | Где используется | Происхождение | Лицензия |
|---|---|---|---|
| `gpt-oss:20b` (OpenAI, открытые веса) | ассистент заявки: извлечение суммы, срока, цели и реквизитов с цитатами (`personalCab/prom_v2/adapters.py`) | скачивается из реестра Ollama при первом запуске (`deploy/ollama_ready.py`), около 14 ГБ | Apache 2.0 и usage policy модели ([OpenAI](https://developers.openai.com/api/docs/models/gpt-oss-20b.md), [Hugging Face](https://huggingface.co/openai/gpt-oss-20b/tree/refs%2Fpr%2F52): файлы `LICENSE`, `USAGE_POLICY`) |
| Скоринговая модель `dt_monotone_v1` (CatBoost) | расчёт PD в `scoring/main` | собственная модель команды; файлы `scoring/main/ml_scoring/model/` (`best_model.cbm`, SHA256 `1e729ce4…2859472b`) | собственная разработка команды |

Скоринговая модель обучена на синтетических данных, без реальных кредитных историй. Это survival-модель на дискретном времени с ограничениями монотонности CatBoost. Методика и метрики: [`scoring/main/ml_scoring/MODEL_REPAIR.md`](scoring/main/ml_scoring/MODEL_REPAIR.md), `validation_report.json`, `test_report.json`. Качество на синтетике не подтверждает калибровку на реальных заёмщиках.

> TODO: обучающий набор указан в коде как `scoring/data/processed/ml_survival_dataset.parquet` (`train_monotone.py`, `best_config.json`). Этого файла в репозитории нет. Нужно уточнить у ML: каким генератором и с какими параметрами он получен и как связан с `scoring/data/final/ml_data_final`.

## Датасеты

Все данные синтетические. Реальные сведения о клиентах, компаниях и сотрудниках не используются.

| Датасет | Где лежит | Как получен | В Docker-образе |
|---|---|---|---|
| Бизнес-БД `business_scoring` v3: 30 компаний, 30 заявок, 32 учётные записи, справочники продуктов R01–R03, политика, ключевая ставка | `scoring/bd/v_3 (actual)/business_scoring_wauth.backup`, `manifest.json` | скрипты команды в `scoring/bd/seeds/` (`seed_aurelius.py`, `seed_test_data.py`, `seed_user_accounts.py`), сценарии в `scoring/bd/scenarios_30.csv`; затем изменения, описанные в `scoring/bd/README_bd.md` (раздел 14) | восстанавливается в том PostgreSQL при первом запуске |
| Синтетические траектории для обучения скоринга | `scoring/data/final/ml_data_final` (parquet), генераторы `scoring/data/generators/` | генераторы команды (`generate_survival*.py`) | нет (`.dockerignore`) |
| Справочник требований к заявкам: 99 требований для R01–R03 | `knowledge/Требования к кредитным заявкам.json` | составлен командой (`knowledge/README.md`) | да, используется RAG ассистента |
| Демо-выписка и перечень полей анкеты | `personalCab/web/data/` | составлены командой | нет (`.dockerignore`) |

Пароли демо-учёток хранятся в БД открытым текстом. Это допущение демо: все учётки синтетические.

## Внешние справочные данные

| Данные | Где используются | Источник |
|---|---|---|
| Ключевая ставка ЦБ 14% (`macro_indicators`, `KEY_RATE`) | лимит PD в экономической политике `AURELIUS_MVP_20261024_V1` | решения Банка России, ссылки в [`scoring/main/decision_engine/BASELINE.md`](scoring/main/decision_engine/BASELINE.md) |
| Ориентир LGD 40% (в политике 45% с буфером) | та же политика | Bank of England, Basel 3.1 IRB, ссылка в `BASELINE.md`; это внешний ориентир, а не норма для МСП |

Обращения к этим источникам во время работы нет: значения записаны в БД.

## Смоделированные интеграции

Доступа к системам Альфа-Банка нет. Внешние источники смоделированы синтетическими данными в таблицах `business_scoring`. Число строк — из `scoring/bd/v_3 (actual)/manifest.json`.

| Интеграция | Как смоделирована в текущей версии |
|---|---|
| Бюро кредитных историй | `credit_obligations` (30 строк) и `credit_repayment_history` (180 строк). Таблица `credit_history_events` пуста. |
| ЕГРЮЛ / ЕГРИП | реквизиты, статус, дата регистрации и ОКВЭД в `companies` (30 строк). Таблица происхождения `company_data_provenance` пуста. |
| ФНС «Прозрачный бизнес» | руководитель, адреса и ОКВЭД в `companies`. Таблица `legal_events` пуста. |
| Реестр МСП | поле `companies.sme_category` |
| Банковская выписка | `bank_transactions` (720 строк, «AURELIUS DEMO BANK») и `financial_statements` (60 строк). PDF и CSV, загруженные клиентом, сохраняются в БД без извлечения данных (`processing_status=STORED_UNVERIFIED`). |
| Подписание документов | не реализовано. Сценарий завершается принятием предложения клиентом. |
| Выдача средств | не реализовано |

## Python-пакеты (runtime, `requirements.lock.txt`)

| Пакет | Версия | Лицензия |
|---|---|---|
| `aiosqlite` | 0.22.1 | MIT License |
| `annotated-types` | 0.8.0 | MIT |
| `anyio` | 4.15.1 | MIT |
| `catboost` | 1.2.10 | Apache License, Version 2.0 |
| `certifi` | 2026.10.23 | Mozilla Public License 2.0 (MPL 2.0) |
| `charset-normalizer` | 3.5.2 | MIT |
| `contourpy` | 1.4.0 | BSD-3-Clause |
| `cycler` | 0.12.1 | BSD License |
| `distro` | 1.9.0 | Apache Software License |
| `et_xmlfile` | 2.0.0 | MIT License |
| `faiss-cpu` | 1.13.2 | MIT AND BSD-3-Clause |
| `fonttools` | 4.67.0 | MIT |
| `graphviz` | 0.21 | MIT |
| `greenlet` | 3.5.6 | MIT AND PSF-2.0 |
| `h11` | 0.16.0 | MIT License |
| `httpcore` | 1.0.9 | BSD-3-Clause |
| `httpcore2` | 2.16.0 | BSD-3-Clause |
| `httpx` | 0.28.1 | BSD License |
| `httpx2` | 2.16.0 | BSD-3-Clause |
| `idna` | 3.20 | BSD-3-Clause |
| `jsonpatch` | 1.37 | BSD-3-Clause |
| `jsonpointer` | 3.5 | BSD License |
| `kiwisolver` | 1.5.1 | BSD License |
| `langchain-core` | 1.5.5 | MIT License |
| `langchain-ollama` | 1.1.0 | MIT License |
| `langchain-protocol` | 0.0.20 | MIT License |
| `langgraph` | 1.2.11 | MIT |
| `langgraph-checkpoint` | 4.3.0 | MIT |
| `langgraph-checkpoint-postgres` | 3.2.0 | MIT |
| `langgraph-checkpoint-sqlite` | 3.1.2 | MIT |
| `langgraph-prebuilt` | 1.1.1 | MIT |
| `langgraph-sdk` | 0.4.9 | MIT |
| `langsmith` | 0.14.12 | MIT License |
| `matplotlib` | 3.11.2 | Python Software Foundation License |
| `narwhals` | 2.27.1 | MIT |
| `numpy` | 2.4.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| `ollama` | 0.6.3 | MIT |
| `openpyxl` | 3.1.5 | MIT License |
| `orjson` | 3.13.0 | MPL-2.0 AND (Apache-2.0 OR MIT) |
| `ormsgpack` | 1.13.0 | Apache-2.0 OR MIT |
| `packaging` | 26.3 | Apache-2.0 OR BSD-2-Clause |
| `pandas` | 2.3.3 | BSD License |
| `pillow` | 13.0.0 | MIT-CMU |
| `plotly` | 7.1.0 | MIT |
| `psycopg` | 3.3.6 | LGPL-3.0-only |
| `psycopg-binary` | 3.3.6 | LGPL-3.0-only |
| `psycopg-pool` | 3.3.3 | LGPL-3.0-only |
| `pydantic` | 2.13.3 | MIT |
| `pydantic_core` | 2.46.3 | MIT |
| `pyparsing` | 3.3.3 | MIT |
| `pypdf` | 6.21.2 | BSD-3-Clause |
| `python-dateutil` | 3.0.0 | Apache Software License; BSD License |
| `pytz` | 2026.5 | MIT License |
| `PyYAML` | 6.0.3 | MIT License |
| `requests` | 2.34.2 | Apache Software License |
| `requests-toolbelt` | 1.0.0 | Apache Software License |
| `scipy` | 1.18.1 | BSD License |
| `six` | 1.17.0 | MIT License |
| `sniffio` | 1.3.1 | Apache Software License; MIT License |
| `SQLAlchemy` | 2.0.51 | MIT |
| `sqlite-vec` | 0.1.9 | MIT License, Apache License, Version 2.0 |
| `tenacity` | 9.2.1 | Apache-2.0 |
| `truststore` | 0.10.5 | MIT |
| `typing-inspection` | 0.4.4 | MIT |
| `typing_extensions` | 4.16.0 | PSF-2.0 |
| `tzdata` | 2026.5 | Apache-2.0 |
| `urllib3` | 2.8.0 | MIT |
| `uuid_utils` | 0.18.0 | BSD-3-Clause |
| `websockets` | 17.3 | BSD-3-Clause |
| `xxhash` | 4.0.2 | BSD-2-Clause |
| `zstandard` | 0.25.0 | BSD-3-Clause |

Обратите внимание: `psycopg`, `psycopg-binary` и `psycopg-pool` распространяются под LGPL-3.0. Они используются как неизменённые библиотеки.

## Python-пакеты только для тестов (`requirements-dev.txt`)

Ставятся только в образ `test` (`docker compose --profile tools`).

| Пакет | Версия | Лицензия |
|---|---|---|
| `pytest` | 9.1.1 | MIT |
| `pluggy` | 1.7.0 | MIT |
| `iniconfig` | 2.3.1 | MIT |
| `Pygments` | 2.21.0 | BSD-2-Clause |

Версии `pluggy`, `iniconfig` и `Pygments` в lock-файле не закреплены. Это версии на момент проверки, 26.10.2026.

## npm-пакеты, входящие в собранный фронт (93)

Это зависимости `dependencies` из `package-lock.json`. Они попадают в статическую сборку `personalCab/web/dist`, включая шрифты Onest и Unbounded (OFL-1.1). Дизайн-токены `@alfalab/core-components-vars` в коде не используются.

| Пакет | Версия | Лицензия |
|---|---|---|
| `@floating-ui/core` | 1.8.0 | MIT |
| `@floating-ui/dom` | 1.8.0 | MIT |
| `@floating-ui/react-dom` | 2.1.9 | MIT |
| `@floating-ui/utils` | 0.2.12 | MIT |
| `@fontsource/onest` | 5.3.1 | OFL-1.1 |
| `@fontsource/unbounded` | 5.3.0 | OFL-1.1 |
| `@radix-ui/number` | 1.1.3 | MIT |
| `@radix-ui/primitive` | 1.2.0 | MIT |
| `@radix-ui/react-accessible-icon` | 1.2.0 | MIT |
| `@radix-ui/react-accordion` | 1.3.1 | MIT |
| `@radix-ui/react-alert-dialog` | 1.2.1 | MIT |
| `@radix-ui/react-arrow` | 1.1.17 | MIT |
| `@radix-ui/react-aspect-ratio` | 1.2.0 | MIT |
| `@radix-ui/react-avatar` | 1.3.1 | MIT |
| `@radix-ui/react-checkbox` | 1.4.1 | MIT |
| `@radix-ui/react-collapsible` | 1.2.1 | MIT |
| `@radix-ui/react-collection` | 1.2.0 | MIT |
| `@radix-ui/react-compose-refs` | 1.1.5 | MIT |
| `@radix-ui/react-context-menu` | 2.4.1 | MIT |
| `@radix-ui/react-context` | 1.3.0 | MIT |
| `@radix-ui/react-dialog` | 1.3.1 | MIT |
| `@radix-ui/react-direction` | 1.2.0 | MIT |
| `@radix-ui/react-dismissable-layer` | 1.2.1 | MIT |
| `@radix-ui/react-dropdown-menu` | 2.2.1 | MIT |
| `@radix-ui/react-focus-guards` | 1.2.0 | MIT |
| `@radix-ui/react-focus-scope` | 1.3.1 | MIT |
| `@radix-ui/react-form` | 0.3.0 | MIT |
| `@radix-ui/react-hover-card` | 1.2.1 | MIT |
| `@radix-ui/react-id` | 1.1.4 | MIT |
| `@radix-ui/react-label` | 2.1.17 | MIT |
| `@radix-ui/react-menu` | 2.2.1 | MIT |
| `@radix-ui/react-menubar` | 1.2.1 | MIT |
| `@radix-ui/react-navigation-menu` | 1.4.1 | MIT |
| `@radix-ui/react-one-time-password-field` | 0.2.1 | MIT |
| `@radix-ui/react-password-toggle-field` | 0.2.1 | MIT |
| `@radix-ui/react-popover` | 1.3.1 | MIT |
| `@radix-ui/react-popper` | 1.4.0 | MIT |
| `@radix-ui/react-portal` | 1.2.0 | MIT |
| `@radix-ui/react-presence` | 1.1.11 | MIT |
| `@radix-ui/react-primitive` | 2.2.0 | MIT |
| `@radix-ui/react-progress` | 1.2.1 | MIT |
| `@radix-ui/react-radio-group` | 1.5.1 | MIT |
| `@radix-ui/react-roving-focus` | 1.2.1 | MIT |
| `@radix-ui/react-scroll-area` | 1.4.0 | MIT |
| `@radix-ui/react-select` | 2.4.1 | MIT |
| `@radix-ui/react-separator` | 1.2.0 | MIT |
| `@radix-ui/react-slider` | 1.6.1 | MIT |
| `@radix-ui/react-slot` | 1.5.0 | MIT |
| `@radix-ui/react-switch` | 1.4.1 | MIT |
| `@radix-ui/react-tabs` | 1.2.1 | MIT |
| `@radix-ui/react-toast` | 1.3.1 | MIT |
| `@radix-ui/react-toggle-group` | 1.2.1 | MIT |
| `@radix-ui/react-toggle` | 1.2.1 | MIT |
| `@radix-ui/react-toolbar` | 1.2.1 | MIT |
| `@radix-ui/react-tooltip` | 1.4.1 | MIT |
| `@radix-ui/react-use-callback-ref` | 1.1.5 | MIT |
| `@radix-ui/react-use-controllable-state` | 1.3.0 | MIT |
| `@radix-ui/react-use-effect-event` | 0.0.5 | MIT |
| `@radix-ui/react-use-escape-keydown` | 1.1.6 | MIT |
| `@radix-ui/react-use-is-hydrated` | 0.1.3 | MIT |
| `@radix-ui/react-use-layout-effect` | 1.1.4 | MIT |
| `@radix-ui/react-use-previous` | 1.1.4 | MIT |
| `@radix-ui/react-use-rect` | 1.1.4 | MIT |
| `@radix-ui/react-use-size` | 1.1.5 | MIT |
| `@radix-ui/react-visually-hidden` | 1.2.13 | MIT |
| `@radix-ui/rect` | 1.1.3 | MIT |
| `@remix-run/route-pattern` | 0.22.1 | MIT |
| `@types/react-dom` | 19.3.0 | MIT |
| `@types/react` | 19.3.0 | MIT |
| `aria-hidden` | 1.2.6 | MIT |
| `class-variance-authority` | 0.7.1 | Apache-2.0 |
| `clsx` | 2.1.1 | MIT |
| `cookie-es` | 3.1.1 | MIT |
| `csstype` | 3.2.3 | MIT |
| `detect-node-es` | 1.1.0 | MIT |
| `framer-motion` | 14.6.0 | MIT |
| `get-nonce` | 1.0.1 | MIT |
| `lucide-react` | 1.61.0 | ISC |
| `motion-dom` | 14.6.0 | MIT |
| `motion-utils` | 14.6.0 | MIT |
| `motion` | 14.6.0 | MIT |
| `radix-ui` | 1.8.1 | MIT |
| `react-dom` | 19.3.1 | MIT |
| `react-remove-scroll-bar` | 2.3.8 | MIT |
| `react-remove-scroll` | 2.7.2 | MIT |
| `react-router` | 8.5.0 | MIT |
| `react-style-singleton` | 2.2.3 | MIT |
| `react` | 19.3.1 | MIT |
| `scheduler` | 0.28.0 | MIT |
| `tailwind-merge` | 3.7.0 | MIT |
| `tslib` | 2.8.1 | 0BSD |
| `use-callback-ref` | 1.3.3 | MIT |
| `use-sidecar` | 1.1.3 | MIT |

## npm-пакеты сборки и тестов (237)

Используются только при сборке и тестах (Vite, TypeScript, Tailwind, ESLint, Vitest и их зависимости). В итоговый образ не входят. Лицензии: MIT — 186, Apache-2.0 — 18, ISC — 12, BSD-2-Clause — 8, MPL-2.0 — 4, BSD-3-Clause — 3, MIT-0 — 2, BlueOak-1.0.0 — 2, CC-BY-4.0 — 1 (`caniuse-lite`), CC0-1.0 — 1. Версии платформенных пакетов (`lightningcss-*`) зависят от ОС сборки; перечень снят на Linux x64.

<details>
<summary>Полный перечень</summary>

| Пакет | Версия | Лицензия |
|---|---|---|
| `@adobe/css-tools` | 4.5.0 | MIT |
| `@asamuzakjp/css-color` | 7.1.7 | MIT |
| `@asamuzakjp/dom-selector` | 10.0.5 | MIT |
| `@babel/code-frame` | 7.29.7 | MIT |
| `@babel/compat-data` | 7.29.7 | MIT |
| `@babel/core` | 7.29.7 | MIT |
| `@babel/generator` | 7.29.8 | MIT |
| `@babel/helper-compilation-targets` | 7.29.7 | MIT |
| `@babel/helper-globals` | 7.29.7 | MIT |
| `@babel/helper-module-imports` | 7.29.7 | MIT |
| `@babel/helper-module-transforms` | 7.29.7 | MIT |
| `@babel/helper-string-parser` | 7.29.11 | MIT |
| `@babel/helper-validator-identifier` | 7.29.7 | MIT |
| `@babel/helper-validator-option` | 7.29.7 | MIT |
| `@babel/helpers` | 7.29.10 | MIT |
| `@babel/parser` | 7.29.11 | MIT |
| `@babel/runtime` | 7.29.10 | MIT |
| `@babel/template` | 7.29.7 | MIT |
| `@babel/traverse` | 7.29.10 | MIT |
| `@babel/types` | 7.29.11 | MIT |
| `@bramus/specificity` | 2.4.3 | MIT |
| `@cacheable/memory` | 2.2.0 | MIT |
| `@cacheable/utils` | 2.5.0 | MIT |
| `@csstools/color-helpers` | 6.1.2 | MIT-0 |
| `@csstools/css-calc` | 3.4.3 | MIT |
| `@csstools/css-color-parser` | 4.2.6 | MIT |
| `@csstools/css-parser-algorithms` | 4.0.2 | MIT |
| `@csstools/css-syntax-patches-for-csstree` | 1.1.15 | MIT-0 |
| `@csstools/css-tokenizer` | 4.0.2 | MIT |
| `@eslint-community/eslint-utils` | 4.10.1 | MIT |
| `@eslint-community/regexpp` | 4.12.2 | MIT |
| `@eslint/config-array` | 0.23.5 | Apache-2.0 |
| `@eslint/config-helpers` | 0.7.0 | Apache-2.0 |
| `@eslint/core` | 1.2.1 | Apache-2.0 |
| `@eslint/js` | 10.0.1 | MIT |
| `@eslint/object-schema` | 3.0.5 | Apache-2.0 |
| `@eslint/plugin-kit` | 0.7.3 | Apache-2.0 |
| `@exodus/bytes` | 1.16.0 | MIT |
| `@humanfs/core` | 0.19.2 | Apache-2.0 |
| `@humanfs/node` | 0.16.8 | Apache-2.0 |
| `@humanfs/types` | 0.15.0 | Apache-2.0 |
| `@humanwhocodes/module-importer` | 1.0.1 | Apache-2.0 |
| `@humanwhocodes/retry` | 0.4.3 | Apache-2.0 |
| `@jridgewell/gen-mapping` | 0.3.13 | MIT |
| `@jridgewell/remapping` | 2.3.5 | MIT |
| `@jridgewell/resolve-uri` | 3.1.2 | MIT |
| `@jridgewell/sourcemap-codec` | 1.6.0 | MIT |
| `@jridgewell/trace-mapping` | 0.3.31 | MIT |
| `@keyv/bigmap` | 1.3.1 | MIT |
| `@keyv/serialize` | 1.1.1 | MIT |
| `@oxc-project/types` | 0.155.0 | MIT |
| `@rolldown/binding-linux-x64-gnu` | 1.2.15 | MIT |
| `@rolldown/pluginutils` | 1.0.1 | MIT |
| `@tailwindcss/node` | 4.3.3 | MIT |
| `@tailwindcss/oxide-linux-x64-gnu` | 4.3.3 | MIT |
| `@tailwindcss/oxide` | 4.3.3 | MIT |
| `@tailwindcss/vite` | 4.3.3 | MIT |
| `@testing-library/dom` | 10.4.2 | MIT |
| `@testing-library/jest-dom` | 7.0.1 | MIT |
| `@testing-library/react` | 16.3.3 | MIT |
| `@testing-library/user-event` | 14.6.8 | MIT |
| `@types/aria-query` | 5.0.4 | MIT |
| `@types/chai` | 5.2.3 | MIT |
| `@types/deep-eql` | 4.0.2 | MIT |
| `@types/esrecurse` | 4.3.1 | MIT |
| `@types/estree` | 1.0.9 | MIT |
| `@types/json-schema` | 7.0.15 | MIT |
| `@types/node` | 26.6.5 | MIT |
| `@typescript-eslint/eslint-plugin` | 8.72.0 | MIT |
| `@typescript-eslint/parser` | 8.72.0 | MIT |
| `@typescript-eslint/project-service` | 8.72.0 | MIT |
| `@typescript-eslint/scope-manager` | 8.72.0 | MIT |
| `@typescript-eslint/tsconfig-utils` | 8.72.0 | MIT |
| `@typescript-eslint/type-utils` | 8.72.0 | MIT |
| `@typescript-eslint/types` | 8.72.0 | MIT |
| `@typescript-eslint/typescript-estree` | 8.72.0 | MIT |
| `@typescript-eslint/utils` | 8.72.0 | MIT |
| `@typescript-eslint/visitor-keys` | 8.72.0 | MIT |
| `@vitejs/plugin-react` | 6.1.2 | MIT |
| `@vitest/mocker` | 5.0.5 | MIT |
| `@vitest/spy` | 5.0.5 | MIT |
| `acorn-jsx` | 5.3.2 | MIT |
| `acorn` | 8.19.0 | MIT |
| `ajv` | 6.15.0 | MIT |
| `ansi-regex` | 5.0.1 | MIT |
| `ansi-styles` | 5.2.0 | MIT |
| `aria-query` | 5.3.0 | Apache-2.0 |
| `assertion-error` | 2.0.1 | MIT |
| `balanced-match` | 4.0.4 | MIT |
| `baseline-browser-mapping` | 2.11.32 | Apache-2.0 |
| `bidi-js` | 1.1.0 | MIT |
| `brace-expansion` | 5.0.12 | MIT |
| `browserslist` | 4.29.4 | MIT |
| `cacheable` | 2.5.0 | MIT |
| `caniuse-lite` | 1.0.30001819 | CC-BY-4.0 |
| `chai` | 6.3.0 | MIT |
| `convert-source-map` | 2.0.0 | MIT |
| `cross-spawn` | 7.0.6 | MIT |
| `css-tree` | 3.2.1 | MIT |
| `css.escape` | 1.5.1 | MIT |
| `data-urls` | 8.0.0 | MIT |
| `debug` | 4.4.3 | MIT |
| `decimal.js` | 10.6.0 | MIT |
| `deep-is` | 0.1.4 | MIT |
| `dequal` | 2.0.3 | MIT |
| `detect-libc` | 2.1.2 | Apache-2.0 |
| `dom-accessibility-api` | 0.5.16 | MIT |
| `dom-accessibility-api` | 0.6.3 | MIT |
| `electron-to-chromium` | 1.5.464 | ISC |
| `enhanced-resolve` | 5.26.0 | MIT |
| `entities` | 8.1.0 | BSD-2-Clause |
| `es-module-lexer` | 2.3.2 | MIT |
| `escalade` | 3.2.0 | MIT |
| `escape-string-regexp` | 4.0.0 | MIT |
| `eslint-plugin-react-hooks` | 7.1.1 | MIT |
| `eslint-plugin-react-refresh` | 0.5.7 | MIT |
| `eslint-scope` | 9.1.2 | BSD-2-Clause |
| `eslint-visitor-keys` | 3.4.3 | Apache-2.0 |
| `eslint-visitor-keys` | 5.0.1 | Apache-2.0 |
| `eslint` | 10.13.0 | MIT |
| `espree` | 11.2.0 | BSD-2-Clause |
| `esquery` | 1.7.0 | BSD-3-Clause |
| `esrecurse` | 4.3.0 | BSD-2-Clause |
| `estraverse` | 5.3.0 | BSD-2-Clause |
| `estree-walker` | 3.0.3 | MIT |
| `esutils` | 2.0.3 | BSD-2-Clause |
| `expect-type` | 1.4.0 | Apache-2.0 |
| `fast-deep-equal` | 3.1.3 | MIT |
| `fast-json-stable-stringify` | 2.1.0 | MIT |
| `fast-levenshtein` | 2.0.6 | MIT |
| `fdir` | 6.5.0 | MIT |
| `file-entry-cache` | 11.1.5 | MIT |
| `find-up` | 5.0.0 | MIT |
| `flat-cache` | 6.1.23 | MIT |
| `flatted` | 3.4.4 | ISC |
| `gensync` | 1.0.0-beta.2 | MIT |
| `glob-parent` | 6.0.2 | ISC |
| `graceful-fs` | 4.2.11 | ISC |
| `hashery` | 1.5.1 | MIT |
| `hermes-estree` | 0.25.1 | MIT |
| `hermes-parser` | 0.25.1 | MIT |
| `hookified` | 1.15.1 | MIT |
| `hookified` | 2.2.0 | MIT |
| `html-encoding-sniffer` | 7.0.0 | MIT |
| `ignore` | 5.3.2 | MIT |
| `ignore` | 7.0.14 | MIT |
| `imurmurhash` | 0.1.4 | MIT |
| `indent-string` | 4.0.0 | MIT |
| `is-extglob` | 2.1.1 | MIT |
| `is-glob` | 4.0.3 | MIT |
| `is-potential-custom-element-name` | 1.0.1 | MIT |
| `isexe` | 2.0.0 | ISC |
| `jiti` | 2.7.0 | MIT |
| `js-tokens` | 4.0.0 | MIT |
| `jsdom` | 30.1.3 | MIT |
| `jsesc` | 3.1.0 | MIT |
| `json-schema-traverse` | 0.4.1 | MIT |
| `json-stable-stringify-without-jsonify` | 1.0.1 | MIT |
| `json5` | 2.2.3 | MIT |
| `keyv` | 5.6.0 | MIT |
| `levn` | 0.4.1 | MIT |
| `lightningcss-linux-x64-gnu` | 1.32.0 | MPL-2.0 |
| `lightningcss-linux-x64-gnu` | 1.33.0 | MPL-2.0 |
| `lightningcss` | 1.32.0 | MPL-2.0 |
| `lightningcss` | 1.33.0 | MPL-2.0 |
| `locate-path` | 6.0.0 | MIT |
| `lru-cache` | 11.5.3 | BlueOak-1.0.0 |
| `lru-cache` | 5.1.1 | ISC |
| `lz-string` | 1.5.0 | MIT |
| `magic-string` | 0.30.21 | MIT |
| `magic-string` | 1.4.3 | MIT |
| `mdn-data` | 2.27.1 | CC0-1.0 |
| `min-indent` | 1.0.1 | MIT |
| `minimatch` | 10.2.6 | BlueOak-1.0.0 |
| `ms` | 2.1.3 | MIT |
| `nanoid` | 3.3.20 | MIT |
| `natural-compare` | 1.4.0 | MIT |
| `node-releases` | 2.0.60 | MIT |
| `obug` | 3.0.0 | MIT |
| `optionator` | 0.9.4 | MIT |
| `p-limit` | 3.1.0 | MIT |
| `p-locate` | 5.0.0 | MIT |
| `parse5` | 8.0.1 | MIT |
| `path-exists` | 4.0.0 | MIT |
| `path-key` | 3.1.1 | MIT |
| `picocolors` | 1.1.1 | ISC |
| `picomatch` | 4.0.7 | MIT |
| `postcss` | 8.5.31 | MIT |
| `prelude-ls` | 1.2.1 | MIT |
| `prettier` | 3.9.10 | MIT |
| `pretty-format` | 27.5.1 | MIT |
| `punycode` | 2.3.1 | MIT |
| `qified` | 0.10.1 | MIT |
| `react-is` | 17.0.2 | MIT |
| `redent` | 3.0.0 | MIT |
| `require-from-string` | 2.0.2 | MIT |
| `rolldown` | 1.2.15 | MIT |
| `saxes` | 6.0.0 | ISC |
| `semver` | 6.3.1 | ISC |
| `semver` | 7.8.5 | ISC |
| `shebang-command` | 2.0.0 | MIT |
| `shebang-regex` | 3.0.0 | MIT |
| `source-map-js` | 1.2.2 | BSD-3-Clause |
| `std-env` | 4.3.0 | MIT |
| `strip-indent` | 3.0.0 | MIT |
| `tailwindcss` | 4.3.3 | MIT |
| `tapable` | 2.3.3 | MIT |
| `tinybench` | 6.2.2 | MIT |
| `tinyexec` | 1.3.1 | MIT |
| `tinyglobby` | 0.2.17 | MIT |
| `tldts-core` | 7.4.19 | MIT |
| `tldts` | 7.4.19 | MIT |
| `tough-cookie` | 6.0.2 | BSD-3-Clause |
| `tr46` | 7.0.0 | MIT |
| `ts-api-utils` | 2.5.0 | MIT |
| `type-check` | 0.4.0 | MIT |
| `typescript-eslint` | 8.72.0 | MIT |
| `typescript` | 6.0.3 | Apache-2.0 |
| `undici-types` | 8.9.0 | MIT |
| `undici` | 8.12.3 | MIT |
| `update-browserslist-db` | 1.3.4 | MIT |
| `uri-js` | 4.4.1 | BSD-2-Clause |
| `vite` | 8.3.5 | MIT |
| `vitest` | 5.0.5 | MIT |
| `w3c-xmlserializer` | 6.0.0 | MIT |
| `webidl-conversions` | 8.0.1 | BSD-2-Clause |
| `whatwg-mimetype` | 5.0.0 | MIT |
| `whatwg-url` | 17.3.0 | MIT |
| `which` | 2.0.2 | ISC |
| `why-is-node-running` | 3.2.1 | MIT |
| `word-wrap` | 1.2.5 | MIT |
| `xml-name-validator` | 5.0.0 | Apache-2.0 |
| `xmlchars` | 2.2.0 | MIT |
| `yallist` | 3.1.1 | ISC |
| `yocto-queue` | 0.1.0 | MIT |
| `zod-validation-error` | 4.0.2 | MIT |
| `zod` | 4.6.7 | MIT |

</details>
