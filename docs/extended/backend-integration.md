# Интеграция кабинета и backend

## Рабочий HTTP-контур

React/TypeScript собирается из personalCab/web; Python [cabinet_server](../../personalCab/prom_v2/cabinet_server.py) обслуживает dist и `/api/v2` с одного origin. PostgreSQL 17 — источник состояния. В [Providers](../../personalCab/web/src/app/context.tsx) `VITE_API_MODE=http` выбирает HttpCreditApi и HttpAuthApi. Иначе подключаются mocks, чьи подпись/выдача не описывают работающий HTTP-контур.

Актуальная спецификация — [OpenAPI](../api/openapi.yaml), запросы — [Postman](../api/aurelius.postman_collection.json), подробные тела — [06 API](../06-api.md). Этот документ объясняет интеграцию и не задаёт параллельную спецификацию.

| Маршрут | Назначение | Потребитель |
|---|---|---|
| POST /api/v2/login, /logout | установка/удаление сессии | HttpAuthApi |
| GET /api/v2/session | восстановление пользователя | HttpAuthApi |
| GET /api/v2/state | проекция компаний, заявок, требований и каталога | HttpCreditApi.refresh |
| POST /api/v2/action | действия kind=credit | HttpCreditApi.command |
| POST /api/v2/documents | action=upload, base64 | HttpCreditApi.uploadDocument |
| GET /api/v2/documents/{id} | байты с контролем владения | ссылка скачивания |

Cookie aurelius_v3: HttpOnly, SameSite=Strict, Path=/api/v2, Max-Age=28800. POST требует Origin, равный `http://`+Host, даже при login/logout. Клиентские role/company_id/user_id не определяют полномочия. Это прямой HTTP-режим; TLS-терминация потребует согласованной настройки Origin и cookie, а не простого размещения за HTTPS.

## Контракты действий и повторы

Оболочка действия: kind, action, request_id, application_id и expected_version; create не требует существующей заявки. В [HttpCreditApi](../../personalCab/web/src/api/HttpCreditApi.ts) revision UI передаётся как expected_version. Денежные NUMERIC сервер сериализует строками, время — ISO. Доменные преобразования адаптера не должны менять единицы ставки.

| Клиент | Сотрудник | Инвариант |
|---|---|---|
| create, save | claim, release | R01–R03; назначение атомарно |
| chat, confirm_facts | verify | предложение отдельно от сохранения; проверка отдельно от исправления данных |
| submit, revise (только API) | score | проверка формы/согласий; финансовые данные читает библиотека |
| answer, upload | review | загрузка сама не закрывает запрос; причина решения обязательна |
| accept, cancel | — | принятие только опубликованного актуального предложения |

`revise` существует в API, но рабочий HTTP-интерфейс его не вызывает. При принятии меняется offer_status=ACCEPTED, а application_status остаётся APPROVED.

`request_id` уникален в рамках пользователя. Сервер сохраняет хэш всего тела и результат: повтор идентичного запроса получает квитанцию, другое тело с тем же ID — REQUEST_ID_REUSED. Адаптер удерживает pending-запрос при сетевой/5xx ошибке; после ответа перечитывает state, при ошибке тоже пытается восстановить реальное состояние. После 4xx pending удаляется: нужно устранить конфликт и создать новое действие, а не слепо менять тело прежнего ID.

## Запись и расчёт

`Cabinet.action` удерживает advisory locks запроса и заявки. Мутация submit/revise и receipt с pending_score фиксируются атомарно. `run_application(...,save=True)` затем выполняет собственную SQLAlchemy-транзакцию. Это **не одна общая транзакция** на весь HTTP-вызов: при отказе расчёта заявка уже может быть отправлена. Повтор того же запроса продолжает pending_score; снимки и отпечатки позволяют определить согласованность расчёта. До повторения необходимо читать состояние.

Скоринг возвращает assessment, recommendation и возможные DRAFT-условия. Ответственный сотрудник делает review APPROVE только при актуальном расчёте и отсутствии открытых дозапросов. Публикация связывает offer, decision и input fingerprint. Клиент видит предложение после одобрения. При accept выполняется повторная проверка; OFFER_STALE снимает предложение и возвращает на рассмотрение.

## Видимость и документы

Клиент получает только свою компанию и её заявки. assessment клиенту всегда null; сотрудник получает assessment, но не приватный dialogue. В текущем main серверный Cabinet.project оставляет клиенту только точные BANK_APPROVE, BANK_REJECT, BANK_REQUEST_DATA; остальные причины, включая иные BANK_*, ему не передаются. Интерфейс представляет сообщения сотрудника. Это исправление c549a06, включённое после исходной подготовки пакета. Внутренние признаки в audit доступны сотруднику через API, хотя интерфейс их не выводит.

Общий генератор [requestId](../../personalCab/web/src/domain/requestId.ts) использует crypto.randomUUID или резерв crypto.getRandomValues, сохраняя UUID v4. ID повторного pending-запроса не меняется. Автозаполнение ОКВЭД берёт companies.okved_main без подстановки названия; историю полей пишет существующий триггер БД без дублирующей ручной вставки. [Состав включённого исправления](../technical/testing/BRANCH_ALIGNMENT_C549A06.md).

PDF/CSV до 10 МиБ передаются JSON/base64, поэтому `/documents` допускает HTTP-тело до 14 МиБ; `/action` ограничен 2 МиБ. Сохраняются байты, SHA256, автор и связь с дозапросом, статус STORED_UNVERIFIED. Извлечение финансов в скоринг не подключено.

## Обработка отказов

401 требует повторного входа; 403 — проверки полномочий/Origin; 409 — обновления состояния и разрешения конфликта; 400 SCORING_INPUT_ERROR — исправления входов; 503 — восстановления сервиса и безопасного повтора. CONFIGURATION_ERROR и SERVICE_UNAVAILABLE не являются кредитным отказом. Для OFFER_STALE чтение state обязательно: техническое изменение сохранено даже при HTTP 409.

Проверки — [test_cabinet](../../personalCab/prom_v2/tests/test_cabinet.py), [документы](../../personalCab/prom_v2/tests/test_cabinet_documents.py), [HTTP UI](../../personalCab/web/src/test/http_credit.test.tsx). Результаты прежних прогонов — [08](../08-testing.md); новый полный runtime-прогон в этой подготовке не выполнен.
