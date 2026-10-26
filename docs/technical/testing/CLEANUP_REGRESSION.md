# Проверка исправлений cleanup-legacy

Дата: 2026-10-26. Ветка: `chore/cleanup-legacy`.

| Проблема | Исправление и результат |
|---|---|
| P0: ОКВЭД с названием | `initialFields` берёт только `companies.okved_main`; название не заменяет отсутствующий код. Подсказка указывает формат `46.90`. Регрессия для R01–R03. |
| P1: UUID по HTTP | Общий UUID v4 через `crypto.randomUUID`, с резервом на `crypto.getRandomValues`. Проверены уникальность, формат и повтор команд/сообщений при 503 с прежним ID при отсутствии `randomUUID`. |
| P1: изоляция экономики | Seed-тесты очищают экономику только внутри откатываемой транзакции; интеграционный тест удаляет только добавленные им ID. Проверка сохранённого лимита учитывает приоритет фактической политики БД над fallback примера. |
| P1: причины в API | Клиент получает только точные коды `BANK_APPROVE`, `BANK_REJECT`, `BANK_REQUEST_DATA`. Сотрудник сохраняет внутренние причины. Реальный CatBoost проверен интеграционными тестами. |
| P1: коллекция | Исходная Postman-коллекция отсутствует в рабочей копии. Добавлена [воспроизводимая замена](postman/cabinet-regression.postman_collection.json) для v4: код ОКВЭД, типизированные синтетические ответы, replay подачи, разграничение клиента/банка, проверка предложения по текущему расчёту. |
| P2: история | Удалена ручная вставка: единственный источник — существующий триггер `trg_log_application_field_values` (есть в v3/v4). Проверены первая запись, повтор без изменения, обновление и сохранение provenance. |

Проверки выполнены на новой отдельной БД `aurelius_test_cleanup_fixes`, восстановленной из `scoring/bd/v_4 (actual)/business_scoring_wauth.backup`. Существующие БД и Docker volumes не восстанавливались и не удалялись.

- Полный Python-набор: **151 passed**, сначала scoring, затем cabinet; повтор на той же БД в обратном порядке: **151 passed**. Три существующих FAISS SWIG DeprecationWarning.
- После обоих прогонов исходные 3 политики `AURELIUS_MVP_20261024_V1` и ключевая ставка 14 сохранены.
- Фронтенд: **232 passed / 14 files**, lint и отдельная HTTP-сборка успешны. Тесты выполняются со штатным mock-режимом по умолчанию; HTTP-режим задаётся для сборки отдельно.
- Newman: **11 requests / 17 assertions / 0 failures**, реальный HTTP API и текущий синтетический дамп.
- Браузер: `http://127.0.0.1:55181`, синтетический клиент и отдельная компания с кодом и названием ОКВЭД. Через UI выполнены создание → заполнение → сохранение → подача заявки №145. Поле содержит `46.90`, итоговый статус «Проверяет специалист». [Снимок результата](cleanup-submitted.png).
- `git diff --check`: успешно.

Подтверждён локальный HTTP-доступ. Внешний адрес демонстрации и HTTPS reverse proxy этим прогоном не проверялись. Сервер сохраняет строгую проверку `Origin == http://Host`; произвольные Forwarded/X-Forwarded-* заголовки не меняют доверенный origin. Для HTTPS-прокси по-прежнему нужна отдельная настройка доверенного публичного origin. При локальном доступе эта настройка не требуется; чужой Origin проверен и получает 403.

Повтор Python-проверок: задать `AURELIUS_TEST_DATABASE_URL` и `DATABASE_URL` на отдельную seeded `aurelius_test*`, добавить корень и `scoring` в `PYTHONPATH`, затем:

```sh
/Users/retro0/projects/PyVenv/venv_core/bin/python -m pytest scoring/main/tests personalCab/prom_v2/tests deploy/tests personalCab/prom/prom_lab/ai_agents_lab/tests -q -p no:cacheprovider
/Users/retro0/projects/PyVenv/venv_core/bin/python -m pytest personalCab/prom_v2/tests deploy/tests personalCab/prom/prom_lab/ai_agents_lab/tests scoring/main/tests -q -p no:cacheprovider
```

Фронтенд (в `personalCab/web`, Node 24): `npm run lint`, `npm test`, затем `VITE_API_MODE=http npm run build`. [Запуск коллекции](postman/README.md).
