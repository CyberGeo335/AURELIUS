# 06. API кабинета `/api/v2`

Проверено на коммите `40b8038` (ветка `test-dev`).

Источник — код `personalCab/prom_v2/cabinet_server.py`, `cabinet.py`, `cabinet_assistant.py`, `cabinet_documents.py`, `cabinet_freshness.py`. Описан только API кабинета v3. Маршрут `/api/chat`, команды прежнего V2 (`command`) и сервер `prom_v2/web_server.py` к текущей версии не относятся.

Машиночитаемое описание — [api/openapi.yaml](api/openapi.yaml) (OpenAPI 3.1). Коллекция запросов со сквозным сценарием — [api/aurelius.postman_collection.json](api/aurelius.postman_collection.json), как её запустить — в [разделе 6](#6-коллекция-запросов). Как устроены потоки внутри сервера — [05-architecture.md](05-architecture.md#3-потоки-данных), статусы заявки — [04-credit-process.md](04-credit-process.md#3-диаграмма-состояний-заявки).

## 1. Общие правила

### 1.1. Маршруты

| Метод | Путь | Сессия | Что делает |
|---|---|---|---|
| `POST` | `/api/v2/login` | не нужна | вход по логину и паролю, ставит cookie |
| `POST` | `/api/v2/logout` | нужна | удаляет сессию, снимает cookie |
| `GET` | `/api/v2/session` | нужна | текущий пользователь |
| `GET` | `/api/v2/state` | нужна | компании, заявки, требования анкеты и каталог, видимые пользователю |
| `POST` | `/api/v2/action` | нужна | все действия с заявками (`kind: "credit"`) |
| `POST` | `/api/v2/documents` | нужна | загрузка документа: то же тело, что у `action`, но только `action: "upload"` |
| `GET` | `/api/v2/documents/{document_id}` | нужна | скачать документ |

Других маршрутов API нет. Любой другой путь без расширения отдаёт `index.html` фронта, путь с расширением — файл из `personalCab/web/dist`.

Неизвестный путь под `/api/`:
- `GET` без сессии — 401 (сессия проверяется раньше маршрута), с сессией — 404 `{"message": "Маршрут не найден."}`;
- `POST` — 404 до всех остальных проверок.

Параметры строки запроса сервер не читает: `GET /api/v2/state?summary=1` отдаёт то же, что `GET /api/v2/state`.

### 1.2. Сессия и cookie

- `POST /api/v2/login` возвращает заголовок:

  ```text
  Set-Cookie: aurelius_v3=<token>; HttpOnly; SameSite=Strict; Path=/api/v2; Max-Age=28800
  ```

- Все остальные маршруты ищут сессию по этой cookie. Нет cookie, сессия истекла (8 часов) или учётка отключена — 401 `{"message": "Войдите в кабинет.", "code": "LOGIN_REQUIRED"}`.
- `POST /api/v2/logout` отвечает `{"authenticated": false}` и `Set-Cookie: aurelius_v3=; …; Max-Age=0`.
- Роль и компания берутся из сессии. Поля `role`, `company_id`, `user_id` в теле запроса игнорируются.

### 1.3. Проверки POST

Проверки идут в таком порядке:

| № | Проверка | Ошибка |
|---|---|---|
| 1 | путь — один из четырёх POST-маршрутов | 404 `{"message": "Маршрут не найден."}` |
| 2 | заголовок `Origin` равен `http://` + значение `Host` | 403 `{"message": "Недопустимый источник запроса."}` (без `code`) |
| 3 | `Content-Length` больше 0 и не больше 2 МиБ (2 097 152 байт); для `/api/v2/documents` — 14 МиБ | 413 `Запрос слишком большой или пустой.` |
| 4 | тело — JSON-объект | не JSON — 400 `INVALID_REQUEST` («Проверьте данные запроса.»); не объект — 400 «Ожидается объект запроса.» |
| 5 | для всех, кроме `login`, — действующая сессия | 401 `LOGIN_REQUIRED` |
| 6 | для `/api/v2/documents` — `action` равно `upload` | 400 «Ожидается загрузка документа.» |

Пример: кабинет открыт по `http://127.0.0.1:5173`, значит запросы должны идти с `Origin: http://127.0.0.1:5173`. Браузер ставит его сам. В Postman и curl заголовок нужно задать явно.

HTTPS не настроен. За HTTPS-прокси `Origin` начнётся с `https://`, и все POST получат 403 ([09-deployment.md](09-deployment.md#8-доступ-с-других-компьютеров)).

### 1.4. Формат ответов и ошибок

- Все ответы API — `application/json; charset=utf-8`, кроме скачивания документа. Заголовки: `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
- Числа `NUMERIC` из БД (суммы, ставки, PD) приходят **строками**: `"1000000.00"`. Даты и время — строки ISO 8601. Поля `JSONB` — как есть (объект, массив или строка).
- Ошибка — объект `{"message": "<текст для пользователя>", "code": "<код>"}`. Исключения: 403 по `Origin` и 404 по маршруту содержат только `message`.

Как исключения переводятся в ответ (`Handler.error`):

| Исключение | Статус | `code` | `message` |
|---|---|---|---|
| `ApiError` кабинета | свой | свой; если не задан — `INVALID_REQUEST` | свой |
| `InputError` скоринга | 400 | `SCORING_INPUT_ERROR` | текст исключения |
| `ValueError`, `TypeError`, `KeyError` (в том числе невалидный JSON) | 400 | `INVALID_REQUEST` | «Проверьте данные запроса.» |
| `ConfigurationError` скоринга | 503 | `CONFIGURATION_ERROR` | «Операция временно недоступна. Обновите заявку и повторите расчёт.» |
| любое другое, в том числе ошибки БД | 503 | `SERVICE_UNAVAILABLE` | то же общее сообщение |

Текст ошибок БД клиенту не передаётся. Например, значение, нарушающее CHECK-ограничение таблицы, даёт 503 `SERVICE_UNAVAILABLE`, а не 400.

### 1.5. Коды ошибок

| `code` | Статус | Когда |
|---|---|---|
| `LOGIN_REQUIRED` | 401 | нет сессии; неверный логин или пароль («Неверный логин или пароль.») |
| `INVALID_REQUEST` | 400, 403, 404, 409, 413 | код по умолчанию для всех ошибок кабинета без своего кода: неверные поля, роль не та («Действие доступно клиенту.», «Действие доступно сотруднику банка.»), заявка или документ не найдены, недопустимый статус, слишком большой файл. Различайте по статусу и `message` |
| `REQUEST_ID_REUSED` | 409 | `request_id` уже использован этим пользователем с другим телом |
| `STALE_CASE_VERSION` | 409 | `expected_version` не равен текущей версии заявки или не целое число |
| `ASSIGNEE_REQUIRED` | 403 | `score`, `verify`, `review` от сотрудника, который не ответственный за заявку |
| `ALREADY_ASSIGNED` | 409 | `claim`, когда у заявки уже есть ответственный |
| `STALE_PROPOSAL` | 409 | `confirm_facts` с `proposal_id`, который уже не текущий |
| `EXTRACTION_UNAVAILABLE` | 503 | `chat`: модель не вернула сведений, подтверждённых цитатами |
| `SCORING_STALE` | 409 | `review APPROVE`: исходные данные расчёта изменились или у расчёта нет отпечатка |
| `OFFER_STALE` | 409 | `accept`: данные изменились, предложение снято, заявка возвращена на рассмотрение |
| `SCORING_INPUT_ERROR` | 400 | `InputError` из `scoring/main` при `submit`, `score`, `revise` |
| `CONFIGURATION_ERROR` | 503 | `ConfigurationError` из `scoring/main` |
| `SERVICE_UNAVAILABLE` | 503 | прочие сбои, в том числе ошибки БД |

## 2. Чтение

### 2.1. `POST /api/v2/login`

Тело: `{"login": "<строка>", "password": "<строка>"}`. Оба поля — непустые строки, иначе 400 «Введите логин и пароль.». Учётка ищется среди активных (`is_active`).

Ответ 200 — тот же объект, что у `/api/v2/session`, плюс cookie.

### 2.2. `GET /api/v2/session`

```json
{
  "user_id": 1,
  "login": "…",
  "first_name": "…",
  "last_name": "…",
  "role": "CLIENT",
  "company_id": 45
}
```

`role` — `CLIENT` или `BANK_EMPLOYEE`. У сотрудника `company_id` всегда `null`, у клиента — всегда задан (ограничение `user_accounts`). Пароль не возвращается никогда.

### 2.3. `GET /api/v2/state`

```json
{
  "companies": [ … ],
  "applications": [ … ],
  "requirements": [ … ],
  "catalog": [ … ]
}
```

| Ключ | Содержимое | Клиент | Сотрудник |
|---|---|---|---|
| `companies` | строки `public.companies` целиком, по `company_id` | только своя компания | все |
| `applications` | проекция заявок (`Cabinet.project`), новые сверху (`application_date DESC, application_id DESC`) | заявки своей компании | все |
| `requirements` | все строки `public.application_field_requirements` (99) по `product_code, field_number` | все | все |
| `catalog` | строки `public.credit_product_terms` активных продуктов, действующие на текущую дату | все | все |

Поля одной заявки в `applications`:

| Поле | Тип | Что это |
|---|---|---|
| все колонки `public.credit_applications` | — | `application_id`, `company_id`, `product_code`, `application_date`, `requested_amount`, `requested_term_days`, `requested_term_months`, `purpose`, `requested_monthly_payment`, `application_status`, `missing_data_status`, `decision_date`, `requested_data_deadline` |
| `version` | integer | версия заявки из `aurelius_cabinet.application_state`; её передают как `expected_version`. Для заявок без строки состояния (заявки дампа) — `1` |
| `form_state` | object | служебное состояние анкеты: `consentBki`, `consentData`, `businessConfirmed` (boolean), `step` |
| `details` | object \| null | строка `public.application_details` |
| `product_details` | object \| null | строка `public.application_product_details` |
| `fields` | array | строки `public.application_field_values`: `field_code`, `field_value`, `value_source`, `verification_status`, `source_reference`, `obtained_at`, `changed_by_type` и др. |
| `requests` | array | строки `public.application_data_requests` (дозапросы) по времени создания |
| `documents` | array | метаданные документов без байтов: `document_id`, `application_id`, `uploaded_by`, `data_request_id`, `filename`, `media_type`, `size`, `sha256`, `source`, `processing_status`, `created_at` |
| `history` | array | события заявки `{event_id, action, created_at}`, новые сверху. Только имена действий, без деталей |
| `assignment` | object \| null | ответственный сотрудник: `employee_id`, `assigned_at`, `first_name`, `last_name` |
| `decision` | string \| null | последнее решение для показа (`APPROVE`, `REJECT`, `REQUEST_DATA`, `MANUAL_REVIEW`) |
| `reasons` | array | причины этого решения `{code, message}` |
| `offer` | object \| null | предложение — см. 2.4 |
| `offer_stale` | object \| null | `{reason}` последнего снятия предложения; только если заявка на рассмотрении и текущего предложения нет или оно `DECLINED` |
| `assessment` | object \| null | результат скоринга — см. 2.4 |
| `verifications` | array | проверки сотрудника — см. 2.4 |
| `dialogue` | object \| null | диалог с ассистентом — см. 2.4 |

Какое решение показывается в `decision` и `reasons`: если после последнего расчёта кабинета нет решения сотрудника (причины `BANK_*`), берётся решение скоринга из этого расчёта, иначе — последнее решение сотрудника ([04-credit-process.md](04-credit-process.md#подписи-статусов-в-интерфейсе)).

### 2.4. Что видит клиент и что видит сотрудник

| Поле | Клиент | Сотрудник |
|---|---|---|
| `offer` | только когда заявка `APPROVED`, а предложение `PROPOSED` или `ACCEPTED`. Пять полей: `offer_id`, `offer_status`, `offered_amount`, `offered_term_months`, `offered_annual_rate_pct`. В остальных случаях `null` | строка `public.application_product_terms` последнего расчёта кабинета в любом статусе (`DRAFT`, `PROPOSED`, `ACCEPTED`, `DECLINED`), со всеми колонками, включая `offered_conditions` |
| `assessment` | всегда `null` | объект `assessment` из снимка последнего расчёта (`Assessment.to_dict()` из `scoring/main` + `persistence`): `decision`, `eligibility_status`, `reasons`, `policy_version`, `offer` (включая график), `scoring` (`pd_by_horizon`, `monthly_hazard`, `cumulative_pd`, `model_version`, `term_months`), `risk_assessment` (лимит PD и экономика), `automatic_recommendation`, `audit` (в том числе признаки модели и их источники), `persistence` (`scoring_result_id`, `decision_id`, `offer_id`). `null`, если расчёта не было |
| `verifications` | всегда `[]` | записи `verify` из журнала: `details` (`kind`, `source_ref`, `comment`), `created_at`, `first_name`, `last_name` |
| `dialogue` | свой диалог по этой заявке: `history` (`[{role, content}]`), `pending` (неподтверждённое предложение ассистента: `proposal_id`, `patch`, `clear_fields`, `quotes`, `source_message_id`, `source_text`, `display_values`) или `null`, `problems`. `null`, если диалога не было | всегда `null`: диалог клиента сотруднику не передаётся |
| `reasons` | причины последнего решения **без фильтра**, в том числе коды скоринга (`BANK_CONFIRMATION_REQUIRED`, `DB_INPUTS_UNAVAILABLE` и др.) | то же |
| `history` | все события заявки, включая имена действий сотрудника (`claim`, `score`, `verify`, `review`), без деталей и без автора | то же |
| остальные поля | одинаково | одинаково |

Про `reasons`: клиенту в интерфейсе показываются только `BANK_APPROVE`, `BANK_REJECT`, `BANK_REQUEST_DATA` — отбор делает фронт (`src/domain/clientReasons.ts`). API отдаёт клиенту все причины последнего решения. Это ограничение текущей версии (Р6 в [02-decisions.md](02-decisions.md#р6-клиенту-показываются-только-причины-сотрудника)).

PD и лимит PD есть только внутри `assessment`, поэтому клиенту они не передаются. Категорий риска в ответах API нет: в `scoring_results.risk_grade` скоринг пишет `UNRATED`, и это поле в `state` не выводится. Отдельного вывода факторов (вкладов признаков в PD) скоринг не формирует. Признаки модели, на которых посчитан результат, лежат в `assessment.audit` и доступны только сотруднику; интерфейс их не показывает.

### 2.5. `GET /api/v2/documents/{document_id}`

- `document_id` — целое число. Не число или документа нет — 404 «Документ не найден.».
- Доступ: клиент — документы заявок своей компании, сотрудник — любые. Документ чужой заявки — 404 «Заявка не найдена.».
- Ответ 200 — байты файла:

  ```text
  Content-Type: application/pdf | text/csv
  Content-Disposition: attachment; filename="document"; filename*=UTF-8''<имя файла>
  Cache-Control: no-store
  X-Content-Type-Options: nosniff
  ```

## 3. Действия: `POST /api/v2/action`

### 3.1. Общее тело и ответ

```json
{
  "kind": "credit",
  "action": "save",
  "request_id": "0d8f5c0e-…",
  "application_id": 123,
  "expected_version": 4,
  "…": "поля действия"
}
```

| Поле | Обязательно | Правило |
|---|---|---|
| `kind` | да | строго `"credit"`, иначе 400 «Неподдерживаемая операция кабинета.» |
| `action` | да | одно из действий ниже, иначе 400 «Неизвестное действие.» (после проверок заявки и версии) |
| `request_id` | да | строка длиной 1–120, иначе 400 «Требуется request_id.». Уникальна в пределах пользователя |
| `application_id` | все, кроме `create` | целое число. Нет заявки или она чужая для клиента — 404 «Заявка не найдена.» |
| `expected_version` | все, кроме `create` | целое число, равное `version` заявки из `state`, иначе 409 `STALE_CASE_VERSION` |

Успешный ответ любого действия — 200:

```json
{"application_id": "123"}
```

`application_id` — строка. Новое состояние читается через `GET /api/v2/state`. Каждое успешное действие увеличивает `version` заявки на 1 и пишет событие в журнал.

### 3.2. Повтор запроса и `request_id`

- Квитанция хранится по паре (пользователь, `request_id`) вместе с SHA-256 всего тела.
- Тот же `request_id` и то же тело — возвращается сохранённый результат, действие не выполняется повторно.
- Тот же `request_id` и другое тело — 409 `REQUEST_ID_REUSED`.
- Ошибка (4xx/5xx) квитанции не оставляет, кроме двух случаев:
  - `submit`, `score`, `revise`: изменение заявки сохранено, а скоринг упал. Повтор того же запроса досчитывает скоринг без повторного изменения;
  - `accept` с 409 `OFFER_STALE`: снятие предложения сохранено, повтор снова вернёт 409 `OFFER_STALE`.
- Для нового действия нужен новый `request_id` и актуальный `expected_version`.

### 3.3. Порядок проверок

1. `kind`, `request_id`, квитанция.
2. Заявка существует и доступна (`404`), версия совпадает (`409 STALE_CASE_VERSION`).
3. Роль: клиентские действия — 403 «Действие доступно клиенту.»; `score`, `verify`, `review` — сначала сотрудник (403 «Действие доступно сотруднику банка.»), затем ответственный (403 `ASSIGNEE_REQUIRED`).
4. Статус заявки и поля действия.

Поэтому запрос от пользователя не той роли, но с устаревшей версией получит 409, а не 403.

### 3.4. Сводная таблица действий

| Действие | Роль | Допустимый статус и условия | Поля тела | Результат |
|---|---|---|---|---|
| `create` | клиент | продукт `R01`, `R02` или `R03` и он активен | `product` | новая заявка `DRAFT`, версия 1 |
| `save` | клиент | `DRAFT` | `patch` | анкета и параметры заявки |
| `submit` | клиент | `DRAFT`, проверки подачи | — | `UNDER_REVIEW` + автоматический скоринг |
| `chat` | клиент | `DRAFT` | `text` | сообщение и предложение ассистента в `dialogue` |
| `confirm_facts` | клиент | `DRAFT`, есть предложение ассистента | `proposal_id` | подтверждённые поля в анкете |
| `claim` | активный сотрудник | `SUBMITTED`, `UNDER_REVIEW`, `AWAITING_DATA`; нет ответственного | — | сотрудник назначен ответственным |
| `release` | ответственный сотрудник | любой | — | назначение снято |
| `score` | ответственный | `SUBMITTED`, `UNDER_REVIEW` | — | новый расчёт |
| `verify` | ответственный | `SUBMITTED`, `UNDER_REVIEW`, `AWAITING_DATA` | `check_kind`, `source_ref`, `comment` | запись проверки в журнале |
| `review` | ответственный | `SUBMITTED`, `UNDER_REVIEW`, `AWAITING_DATA`; есть расчёт | `decision`, `reason`, `field_code` | решение сотрудника |
| `answer` | клиент | `AWAITING_DATA` | `data_request_id`, `answer` | ответ на дозапрос |
| `accept` | клиент | `APPROVED`, предложение `PROPOSED` | `offer_id` | предложение `ACCEPTED` |
| `revise` | клиент | `APPROVED`, предложение `PROPOSED` | `amount`, `term` | `UNDER_REVIEW` + скоринг |
| `cancel` | клиент | не `REJECTED` и не `CANCELLED`; нет принятого предложения | — | `CANCELLED` |
| `upload` | клиент или сотрудник | любой статус | `filename`, `content_base64`, `data_request_id` | документ сохранён |

Ниже — каждое действие подробно. Тексты ошибок приведены как в коде. Код ошибки, если не указан, — `INVALID_REQUEST`.

### 3.5. `create`

Тело: `{"kind": "credit", "action": "create", "request_id": "…", "product": "R01"}`. `application_id` и `expected_version` не нужны.

- Создаёт `credit_applications` (`DRAFT`, `missing_data_status=PARTIAL`) для компании клиента и строку версии `aurelius_cabinet.application_state` (версия 1).
- Ошибки: 403 «Действие доступно клиенту.»; 400 «Выберите доступный продукт.».

### 3.6. `save`

```json
{
  "kind": "credit", "action": "save", "request_id": "…",
  "application_id": 123, "expected_version": 1,
  "patch": {
    "amount": "1000000",
    "term": 12,
    "purpose": "Пополнение оборотных средств",
    "fields": {"R01_01": "R01", "R01_03": "7701234567", "R01_31": "Подтверждаю"},
    "details": {"contact_full_name": "…", "signer_full_name": "…"},
    "product_details": {"max_tranche_term_value": 6, "max_tranche_term_unit": "MONTHS"},
    "consentBki": true, "consentData": true, "businessConfirmed": true,
    "step": 4
  }
}
```

Все ключи `patch` необязательны; отсутствующий ключ не меняет значение.

| Ключ | Куда пишется | Правило |
|---|---|---|
| `amount` | `credit_applications.requested_amount` | положительное число (строкой или числом) |
| `term` | `credit_applications.requested_term_months` | положительное целое |
| `purpose` | `credit_applications.purpose` | строка или `null` |
| `fields` | `application_field_values` + `application_field_history` | `{field_code: строка до 10 000 символов}`. Код должен быть в `application_field_requirements` продукта заявки. Значение сохраняется с `value_source=CLIENT`, `verification_status=UNVERIFIED`, `changed_by_type=CLIENT`. Неизменённое значение не пишется |
| `details` | `application_details` | только ключи `contact_full_name`, `contact_role`, `contact_phone`, `signer_full_name`, `signer_authority_basis`, `guarantor_participation`, `proposed_collateral`. Пустая строка записывается как `null` |
| `product_details` | `application_product_details` | только `max_tranche_term_value`, `max_tranche_term_unit` (`DAYS` / `MONTHS`), `drawdown_period_months`, `is_revolving`, `overdraft_account_ref` (20 цифр), `overdraft_bank_name`, `overdraft_bank_bik` (9 цифр) |
| `consentBki`, `consentData`, `businessConfirmed` | `aurelius_cabinet.application_state.form_state` | только `true` / `false` |
| `step` | `form_state.step` | шаг формы в интерфейсе, сервер его не проверяет |

Данные компании (`public.companies`) действие не меняет: поля анкеты с реквизитами компании хранятся как значения анкеты от клиента.

Также сбрасывает неподтверждённое предложение ассистента в диалоге заявки.

Ошибки: 403 «Действие доступно клиенту.»; 409 «Редактировать можно только черновик.»; 400 «Неверные данные формы.», «Сумма: укажите положительное число.», «Срок: укажите положительное целое число.», «Неверная цель кредита.», «Значение поля должно быть текстом до 10000 символов.», «Поле не относится к продукту.», «Неизвестное поле анкеты.», «Согласие должно быть явным.». Значение, нарушающее CHECK таблицы (например, `max_tranche_term_unit: "WEEKS"`), — 503 `SERVICE_UNAVAILABLE`.

### 3.7. `submit`

Тело — только общие поля. Проверки (`validate_submission`), по порядку:

1. `requested_amount` — положительное число, `requested_term_months` — положительное целое.
2. Заполнена цель (`purpose`).
3. Три согласия в `form_state` равны `true`.
4. Заполнены все поля продукта, обязательные для типа компании: `required_ooo` для юрлица, `required_ip` для ИП. Для R01 это 29 полей у юрлица и 24 у ИП (посчитано по `knowledge/Требования к кредитным заявкам.json`).
5. `<продукт>_01` равно коду продукта; `<продукт>_03` равно ИНН компании (если ИНН у компании есть).
6. ИНН в анкете — 10 или 12 цифр.
7. `<продукт>_05` и `<продукт>_06` равны сумме и сроку заявки.
8. `<продукт>_31` равно `Подтверждаю`.
9. Для R02 и R03 — заполнены `product_details.max_tranche_term_value` и `max_tranche_term_unit` (`DAYS` / `MONTHS`).

Результат: `application_status=UNDER_REVIEW`, `missing_data_status=COMPLETE`, `application_details.confirmed_at`, `confirmation_version=cabinet-v3-1`. Затем сразу автоматический скоринг ([05-architecture.md](05-architecture.md#31-подача-заявки-и-автоматический-скоринг)).

Ошибки проверок — 400: «Укажите цель кредита.», «Подтвердите сведения и согласия.», «Заполните обязательные поля: <список подписей>», «Продукт и ИНН должны совпадать с данными заявки.», «ИНН должен содержать 10 или 12 цифр.», «Сумма и срок анкеты не совпадают с параметрами заявки.», «Подтвердите корректность анкеты.», «Укажите отдельный срок транша и единицу измерения.». Статус — 409 «Заявка уже отправлена.».

Ошибки скоринга (заявка уже `UNDER_REVIEW`, см. 3.2): 400 `SCORING_INPUT_ERROR`, 503 `CONFIGURATION_ERROR` / `SERVICE_UNAVAILABLE`, 409 «Не найден снимок расчёта. Повторите скоринг.».

На исходном дампе скоринг завершается без ошибки HTTP: решение `MANUAL_REVIEW` с причиной `DB_INPUTS_UNAVAILABLE`, без PD и без предложения ([02-decisions.md](02-decisions.md#ограничения-текущей-версии)).

### 3.8. `chat`

Тело: общие поля + `"text": "<сообщение>"`.

- Только клиент и только `DRAFT`.
- Справочный вопрос о требованиях (определяется `is_requirements_question`) обслуживает RAG; иначе модель извлекает сумму, срок, цель, ИНН, форму бизнеса и характер потребности с цитатами из сообщения.
- Результат — в `dialogue` заявки: новые сообщения в `history`, неподтверждённое предложение в `pending`. Анкету `chat` не меняет.
- Ошибки: 403 «Действие доступно клиенту.»; 409 «Диалог заполняет только черновик. Для дозапроса используйте отдельный ответ.»; 400 «Введите сообщение до 12000 символов.» (пустое после обрезки пробелов или длиннее 12 000); 503 `EXTRACTION_UNAVAILABLE` «Ollama не вернула проверяемые сведения. Повторите сообщение или заполните форму.». При 503 ничего не сохраняется.

### 3.9. `confirm_facts`

Тело: общие поля + `"proposal_id": "<dialogue.pending.proposal_id>"`.

- Переносит в анкету подтверждённые значения: сумму (`amount` и `_05`), срок (`term` и `_06`), цель (`purpose` и `_04`), ИНН (`_03`), форму бизнеса (`_02`, для юрлица также `_12`). Запись идёт так же, как в `save` (`CLIENT`, `UNVERIFIED`).
- Ошибки: 409 `STALE_PROPOSAL` «Предложение изменилось. Проверьте актуальные сведения.»; 409 «Удаление сведений требует отдельного редактирования формы. Уточните сообщение без удаления.»; 409 «ИНН не совпадает с вашей компанией. Требуется проверка сотрудника.»; 409 «Форма бизнеса отличается от записи компании. Требуется проверка сотрудника.». Плюс ошибки роли и статуса, как у `chat`.

### 3.10. `claim` и `release`

Тело — только общие поля.

- `claim`: назначает текущего сотрудника ответственным (`aurelius_cabinet.assignments`). Ошибки: 403 «Действие доступно сотруднику банка.»; 403 «Требуется активный сотрудник банка.»; 409 «Взять в работу можно заявку на рассмотрении.»; 409 `ALREADY_ASSIGNED` «У заявки уже есть ответственный.».
- `release`: снимает назначение. Статус заявки не проверяется. Ошибки: 403 «Действие доступно сотруднику банка.»; 403 «Освободить можно только свою заявку.».

Ответственный нужен для `score`, `verify` и `review`. Без назначения они дают 403 `ASSIGNEE_REQUIRED` «Действие доступно ответственному сотруднику. Сначала возьмите заявку в работу.».

### 3.11. `score`

Тело — только общие поля. Повторный расчёт тем же путём, что после `submit`. Ошибки: 403 `ASSIGNEE_REQUIRED`; 409 «Скоринг доступен для отправленной заявки.» (статус не `SUBMITTED` / `UNDER_REVIEW`, в том числе `AWAITING_DATA`); ошибки скоринга, как у `submit`.

### 3.12. `verify`

```json
{"…": "общие поля", "check_kind": "revenue", "source_ref": "Выписка за 09.2026", "comment": "Выручка совпадает с анкетой"}
```

- `check_kind` — `authority` (полномочия подписанта) или `revenue` (выручка); `source_ref` — непустая строка до 1000 символов; `comment` — непустая строка до 10 000.
- Пишет событие `verify` с `details: {kind, source_ref, comment}`. Данные компании и статусы полей анкеты не меняются (Р12).
- Ошибки: 403 `ASSIGNEE_REQUIRED`; 409 «Заявка закрыта для проверки.»; 400 «Укажите вид проверки, источник и комментарий.».

### 3.13. `review`

```json
{"…": "общие поля", "decision": "REQUEST_DATA", "reason": "Уточните фактический адрес", "field_code": "R01_20"}
```

| Поле | Правило |
|---|---|
| `decision` | `APPROVE`, `REJECT` или `REQUEST_DATA` |
| `reason` | непустая строка. Сохраняется как причина `BANK_<decision>`; для `REQUEST_DATA` — ещё и как текст вопроса клиенту |
| `field_code` | только для `REQUEST_DATA`: код поля из требований продукта заявки |

Проверки по порядку:
1. Статус `SUBMITTED`, `UNDER_REVIEW` или `AWAITING_DATA`, иначе 409 «Заявка недоступна для решения.».
2. `decision` и `reason`, иначе 400 «Укажите решение и его причину.».
3. Есть расчёт кабинета и его решение, иначе 409 «Сначала выполните скоринг.».
4. Для `APPROVE`:
   - у расчёта есть предложение `DRAFT`, иначе 409 «Для одобрения нужен рассчитанный черновик предложения.»;
   - отпечаток входов актуален, иначе 409 `SCORING_STALE`;
   - нет открытых дозапросов, иначе 409 «Сначала дождитесь ответов на открытые запросы.».
5. Для `REQUEST_DATA`: поле относится к продукту, иначе 400 «Выберите поле для уточнения.».

Результат:

| `decision` | Статус заявки | Что ещё |
|---|---|---|
| `APPROVE` | `APPROVED`, `decision_date` | `credit_decisions` с `approved_amount`; предложение `PROPOSED`; запись `offer_publications` |
| `REJECT` | `REJECTED`, `decision_date` | `credit_decisions`; предложения `DRAFT` / `PROPOSED` → `DECLINED` |
| `REQUEST_DATA` | `AWAITING_DATA`, `decision_date` | `credit_decisions`; новая строка `application_data_requests` (`OPEN`) |

На исходном дампе `APPROVE` всегда даёт 409 «Для одобрения нужен рассчитанный черновик предложения.»: скоринг не строит предложение ([02-decisions.md](02-decisions.md#ограничения-текущей-версии)). `REJECT` и `REQUEST_DATA` работают.

### 3.14. `answer`

```json
{"…": "общие поля", "data_request_id": 7, "answer": "г. Москва, ул. …"}
```

- `data_request_id` — `request_id` из `applications[].requests` (открытый запрос этой заявки); `answer` — непустая строка до 10 000 символов.
- Записывает ответ в поле анкеты `field_code` запроса (`CLIENT`, `UNVERIFIED`) и в `answer_value`, ставит запрос `ANSWERED`. Если открытых запросов не осталось, заявка возвращается в `UNDER_REVIEW`. Повторный скоринг сам не запускается.
- Ошибки: 403 «Действие доступно клиенту.»; 409 «Заявка не ожидает ответа.»; 400 «Укажите ответ на открытый запрос.»; 400 «Значение поля должно быть текстом до 10000 символов.».

Файл к дозапросу прикладывается отдельным `upload` с `data_request_id`; сам `upload` запрос не закрывает.

### 3.15. `accept`

Тело: общие поля + `"offer_id": <applications[].offer.offer_id>` (число или строка).

- Сверяет, что предложение — текущее и `PROPOSED`, а расчёт, решение и предложение не изменились с момента одобрения ([05-architecture.md](05-architecture.md#33-принятие-предложения-клиентом)).
- Успех: `offer_status=ACCEPTED`, статус заявки остаётся `APPROVED`. Это конец сценария в текущей версии: подписание и выдача не реализованы (Р14).
- Ошибки: 403 «Действие доступно клиенту.»; 409 «Нет одобренного предложения.»; 409 «Предложение изменилось.»; 409 `OFFER_STALE` «Данные изменились, банк повторно проверяет предложение.» — предложение снято (`DECLINED`), заявка в `UNDER_REVIEW`.

### 3.16. `revise`

Тело: общие поля + `"amount": <число>`, `"term": <целое>`.

- Только при `APPROVED` и предложении `PROPOSED`. Снимает предложения `DRAFT` / `PROPOSED`, записывает новые сумму и срок, переводит заявку в `UNDER_REVIEW` и запускает скоринг.
- В интерфейсе не используется.
- Ошибки: 409 «Изменить можно только предложенные условия.»; 400 «Сумма: …», «Срок: …»; ошибки скоринга.

### 3.17. `cancel`

Тело — только общие поля.

- Статус → `CANCELLED`; предложения `DRAFT` / `PROPOSED` → `DECLINED`; открытые дозапросы → `CANCELLED`.
- Ошибки: 403 «Действие доступно клиенту.»; 409 «Заявка закрыта.» (`REJECTED` или `CANCELLED`); 409 «Предложение уже принято.».

### 3.18. `upload` (через `/api/v2/documents`)

```json
{
  "kind": "credit", "action": "upload", "request_id": "…",
  "application_id": 123, "expected_version": 6,
  "filename": "vypiska.csv",
  "content_base64": "ZGF0ZSxhbW91bnQKMjAyNi0wOS0wMSwxMDAwCg==",
  "data_request_id": 7
}
```

| Поле | Правило |
|---|---|
| `filename` | 1–200 символов, без `/`, `\` и управляющих символов; расширение `.pdf` или `.csv` |
| `content_base64` | строгий base64; после декодирования 1 байт — 10 МиБ |
| `data_request_id` | необязательно; положительное целое — открытый дозапрос этой заявки |

Проверка содержимого:
- PDF — начинается с `%PDF-`, в последних 1024 байтах есть `%%EOF`;
- CSV — UTF-8 (BOM допускается), без управляющих символов, кроме `\r\n\t`, разделитель `,`, `;` или табуляция, не меньше 2 колонок, у всех строк одинаковое число колонок.

Результат: строка `aurelius_cabinet.documents` (`source=CLIENT_UPLOAD` или `EMPLOYEE_UPLOAD`, `processing_status=STORED_UNVERIFIED`, SHA-256), событие `upload`. Данные из файла никуда не извлекаются (Р13).

Доступ: клиент — к заявкам своей компании, сотрудник — к любой заявке, назначение не требуется. Статус заявки не проверяется.

Ошибки: 400 «Недопустимое имя файла.», «Допускаются только PDF и CSV.», «Не удалось прочитать содержимое файла.», «Файл не соответствует формату PDF.», «CSV должен быть в UTF-8 с одинаковым числом колонок и разделителем , ; или табуляцией.», «Недопустимый идентификатор дозапроса.»; 413 «Размер файла не должен превышать 10 МиБ.», «Файл пуст или превышает 10 МиБ.»; 409 «Открытый дозапрос этой заявки не найден.».

`action: "upload"` принимает и `/api/v2/action`, но с лимитом тела 2 МиБ. Фронт отправляет загрузку на `/api/v2/documents`.

## 4. Примеры curl

Без браузера нужно самим передавать `Origin` и cookie. Логин и пароль — из БД стенда ([07-data-model.md](07-data-model.md#7-тестовые-учётные-записи)).

```sh
BASE=http://127.0.0.1:5173
curl -s -c client.txt -H "Origin: $BASE" -H 'Content-Type: application/json' \
  -d '{"login":"<логин клиента>","password":"<пароль>"}' $BASE/api/v2/login
curl -s -b client.txt $BASE/api/v2/state
curl -s -b client.txt -H "Origin: $BASE" -H 'Content-Type: application/json' \
  -d '{"kind":"credit","action":"create","request_id":"demo-1","product":"R01"}' $BASE/api/v2/action
```

## 5. Чего нет в API

- Подписания документов и выдачи средств (Р14).
- Серверной фильтрации причин для клиента (Р6).
- Пагинации и фильтров в `state`: сотрудник получает все заявки сразу.
- Отдельного эндпоинта журнала событий: в `state` есть только `history` (имена действий) и `verifications`.
- Ограничения частоты запросов и блокировки после неудачных входов.

Во фронте (`src/api/HttpV2Api.ts`) остались методы прежнего V2 API (`operations`, `operation`, `catalog`, `audit`, `review-preview`). Кабинет v3 эти маршруты не обслуживает, текущий интерфейс их не вызывает.

## 6. Коллекция запросов

Файл: [api/aurelius.postman_collection.json](api/aurelius.postman_collection.json) (Postman Collection v2.1, 69 запросов). Открывается в Postman («Import») или запускается из командной строки через newman.

Переменные коллекции (значения логинов и паролей в файле пустые, задавайте их в окружении или при запуске):

| Переменная | Что это |
|---|---|
| `baseUrl` | адрес кабинета, например `http://127.0.0.1:5173` |
| `clientLogin`, `clientPassword` | клиент юрлица без намеренных пропусков реквизитов (`company_id` 45–64, см. [07-data-model.md](07-data-model.md#6-синтетические-данные)) |
| `employeeLogin`, `employeePassword` | сотрудник банка |

Папки:

| Папка | Что проверяет |
|---|---|
| `01 Сквозной сценарий` | клиент: вход → `create` R01 → `state` → `save` → `submit`; сотрудник: вход → `claim` → `score` → `verify` → `review REQUEST_DATA`; клиент: `answer` + `upload` CSV; сотрудник: скачивание документа → `review REJECT`; клиент видит `REJECTED` и причину `BANK_REJECT` |
| `02 Отмена черновика` | `create` → `cancel` → `CANCELLED` |
| `03 Негативные проверки` | 401 без сессии, 403 чужой `Origin`, 409 `STALE_CASE_VERSION`, 409 `REQUEST_ID_REUSED`, 403 `ASSIGNEE_REQUIRED` |
| `04 Ожидаемая ошибка на исходном дампе` | `review APPROVE` по расчёту без предложения → 409 |

Особенности:
- Клиент и сотрудник работают в разных папках, и каждая папка начинается со входа. Ответ на вход заменяет cookie `aurelius_v3` в хранилище cookie Postman / newman, поэтому дальше запросы идут от нового пользователя.
- У всех POST есть заголовок `Origin: {{baseUrl}}`.
- `request_id` генерируется для каждого запроса (`{{$guid}}`), `expected_version` берётся из последнего `GET /api/v2/state`. Идентификаторы заявки, дозапроса и документа передаются между запросами через переменные коллекции.
- Анкета в `save` собирается скриптом из `state.requirements` и данных компании так же, как это делает фронт (`src/domain/formSteps.ts`, `initialFields`).
- Каждый прогон создаёт на стенде 4 новые заявки: по одной в каждой папке. Это нормально для отдельного стенда; на рабочей установке коллекцию не запускайте.

Запуск через Docker (newman ставить не нужно):

```sh
docker run --rm --network <проект>_default -v "$PWD/docs/api:/etc/newman" postman/newman:6.1.3 \
  run aurelius.postman_collection.json \
  --env-var baseUrl=http://app:5173 \
  --env-var clientLogin=<логин> --env-var clientPassword=<пароль> \
  --env-var employeeLogin=<логин> --env-var employeePassword=<пароль>
```

`<проект>` — значение `COMPOSE_PROJECT_NAME` (по умолчанию `aurelius`). Внутри сети Docker кабинет доступен как `http://app:5173`; сервер сверяет `Origin` с `Host`, поэтому `baseUrl` должен совпадать с адресом, по которому идут запросы.

Прогон 26.10.2026 на стенде из чистой копии `40b8038` (Docker Desktop, Windows; `postman/newman:6.1.3` в сети стенда, `baseUrl=http://app:5173`, клиент — юрлицо `company_id=45`):

| Показатель | Значение |
|---|---|
| Запросов | 69, упало 0 |
| Проверок (assertions) | 136, упало 0 |
| Скриптов | 72 (69 тестовых, 3 перед запросом), упало 0 |
| Время прогона | 5,4 с; самый долгий запрос — `submit` с автоматическим скорингом, 1 033 мс |
| Решение скоринга после `submit` и `score` | `MANUAL_REVIEW`, причина `DB_INPUTS_UNAVAILABLE`: «DB proxy needs 13 complete positive-revenue months; no zero-filling missing history», PD не рассчитана |
| Созданные заявки | 4 (`application_id` 65–68) |

Подробный разбор прогонов будет в [08-testing.md](08-testing.md).
