# Источники и итоговая проверка

Срез: origin/main `68b7b57c0e501e4575bc2a10eee20e6e42f529d4`, коммит 26.10.2026 16:14:32 +03:00. origin: [CyberGeo335/AURELIUS](https://github.com/CyberGeo335/AURELIUS). Получение origin/main выполнено до извлечения git archive. Документы подготовлены в локальной копии этого коммита; исходная ветка score-dev не переключалась.

## Проверки этой подготовки

Этот раздел фиксирует исходную подготовку на 68b7b57. При переносе в main 138b799 обновлены сведения о серверной фильтрации причин, UUID, автозаполнении ОКВЭД и записи истории; основной комплект 00–11 сохранён. Новая статическая проверка выполняется отдельно: [integration-validation-results.json](integration-validation-results.json). Старые [validation-results.json](validation-results.json) и [source-integrity.json](source-integrity.json) сохранены как протоколы исходной подготовки и не подменяются новыми результатами.

Текущий инвентарь — 156 Python и 232 frontend cases. Его выполнение/сбор на объединённой версии описаны в [основном протоколе](../technical/testing/CORE_DOCS_VALIDATION.json) и [08](../08-testing.md). При импорте расширенной части новый pytest/Vitest/Docker/БД/Ollama-прогон не выполнялся: проверены документы, схема, модель и статический инвентарь.

`python docs/extended/check_docs.py` проверяет локальные Markdown-ссылки и якоря, наличие всех public-таблиц и колонок справочника, количество ADR, SHA256 модели и статический инвентарь тестов. [Очищенный результат](validation-results.json) содержит полный перечень файлов и счётчики. Скрипт не выполняет pytest/Vitest и не вызывает БД/Ollama. Статические счётчики: Python 155 случаев, фронт 228; deploy/test_launch — 15. Учтены литеральные параметризации Python, it.each и describe.each текущих исходников; такой подсчёт не является универсальным сборщиком тестов для будущего произвольного синтаксиса.

Проверка неизменности исходного приложения по Git blob hash с учётом CRLF/LF-преобразования Windows при git archive сохранена в [source-integrity.json](source-integrity.json). Меняются только документация и её проверочный скрипт; финансовая политика, модель, DDL, данные и приложение не редактировались.

## Прочитанные и сопоставленные источники

| Группа | Источники | Что подтверждено |
|---|---|---|
| Рамки | [AGENTS](../../AGENTS.md), [кейс](../case/ABOUT.md), [требования](../case/REQUIREMENTS.md), основной docs/00–09 | роли, границы, источники и краткий маршрут |
| Решения | [02](../02-decisions.md) | 16 решений, трассировка ADR |
| HTTP и запись | [server](../../personalCab/prom_v2/cabinet_server.py), [cabinet](../../personalCab/prom_v2/cabinet.py), [freshness](../../personalCab/prom_v2/cabinet_freshness.py), [documents](../../personalCab/prom_v2/cabinet_documents.py) | роли, Origin/cookie, блокировки, транзакции и проекции |
| Ассистент | [bridge](../../personalCab/prom_v2/cabinet_assistant.py), [Agent](../../personalCab/prom_v2/agent.py), [adapters](../../personalCab/prom_v2/adapters.py), [RAG](../../personalCab/prom/rag/pipeline.py), [факты](../../personalCab/prom_v2/declared_facts.py), [tests](../../personalCab/prom_v2/tests/) | ограниченные команды, подтверждение, валидация и контракты тестов |
| ML | [артефакты](../../scoring/main/ml_scoring/model/), [predictor](../../scoring/main/ml_scoring/predictor.py), [feature_builder](../../scoring/main/ml_scoring/feature_builder.py), [обучение](../../scoring/main/ml_scoring/train_monotone.py), [holdout](../../scoring/main/ml_scoring/validate_monotone_release.py), [promotion](../../scoring/main/ml_scoring/promote_monotone.py) | версия, SHA256, признаки, метрики и формулы |
| Исследовательские данные | [генератор v2](../../scoring/data/generators/generate_survival_v2.py), [подготовка](../../scoring/notebooks/01_prepare_survival.ipynb), [split](../../scoring/notebooks/02_train_survival.ipynb) | синтетическое событие, цензурирование и различие split |
| БД | [DDL](../../scoring/bd/v_4%20(actual)/schema_actual.sql), [manifest](../../scoring/bd/v_4%20(actual)/manifest.json), [миграции](../../personalCab/prom_v2/migrations/), [restore](../../deploy/00_restore.sh) | 35+10+1 таблиц, все поля, ключи и начальные числа |
| Фронт | [App](../../personalCab/web/src/app/App.tsx), [Providers](../../personalCab/web/src/app/context.tsx), [HttpCreditApi](../../personalCab/web/src/api/HttpCreditApi.ts), [HttpAuthApi](../../personalCab/web/src/api/HttpAuthApi.ts), [CSS](../../personalCab/web/src/styles/index.css), [тесты](../../personalCab/web/src/test/) | маршруты, HTTP/mock, состояния и desktop-ограничение |
| Запуск | [start.ps1](../../start.ps1), [Postgres.Dockerfile](../../deploy/Postgres.Dockerfile), [launch tests](../../deploy/tests/test_launch.py) | Windows-исправления и инвентарь 15 |
| Протокол | [AUR-01–10](../technical/testing/LLM_SCENARIOS_01_10_RESULTS.json), [методика](../technical/testing/LLM_SCENARIOS_01_10_FIXES.md) | существующий прогон, отдельно от этой подготовки |

## Исправленные расхождения

- Инвентарь Python 150 → 155: новые пять проверок Windows-запуска. Фронт 228 подтверждён статическим пересчётом.
- Установленная модель описана по candidate текущих отчётов: Brier хуже baseline, max calibration test лучше; 15 признаков с month_on_book.
- debt_to_revenue описан как synthetic proxy, revenue_trend_12m отделён от экспериментального current_revenue_trend_3m.
- Публикация оффера отделена от расчёта, принятие — от подписи/выдачи; application_status после accept остаётся APPROVED.
- В исходном срезе 68b7b57 отбор reasons выполнял фронт. При интеграции актуализированы ADR-006, HTTP-контракт и требования интерфейса: в main уже действует серверный allowlist точных BANK_APPROVE/BANK_REJECT/BANK_REQUEST_DATA из c549a06.
- Мобильная адаптивность не заявлена при body min-width=1260px; текст ErrorBoundary о хранении в браузере отмечен как несоответствие HTTP-режиму.

## Неподтверждённое и будущие проверки

В среде исходной подготовки локальные E:/Work источники отсутствовали: исследование, V2-референсы и полный протокол 30 заявок в пакет не включались. При импорте доступен опубликованный в main [протокол 30 сценариев](../technical/testing/SCENARIOS_30.md); он используется как самостоятельный источник с собственной версией. Внешняя страница ЦБ была прочитана автором исходного пакета, два обращения к страницам Альфа-Банка завершились 502: текущие тарифы не заявлены. Это история обращений исходной подготовки, не новое посещение при импорте. Новый Docker/HTTP/БД/Ollama-прогон, браузерная приёмка и измерения бизнес-эффекта при импорте не выполнялись.

Полная побитная реконструкция обучающего parquet из доступного генератора без манифеста происхождения не подтверждена. Для последующего ML-аудита нужны входной parquet, его происхождение и проверка split/отсутствия пересечения заёмщиков. Эти ограничения не мешают идентифицировать загружаемую модель и прочитать сохранённые отчёты, но отделены от воспроизводимого переобучения.
