# Справочник БД: v4 и служебные схемы

Версия кода — [PROGRESS](PROGRESS.md). Основа: [DDL v4](../../scoring/bd/v_4%20(actual)/schema_actual.sql), [manifest](../../scoring/bd/v_4%20(actual)/manifest.json), миграции [005–009](../../personalCab/prom_v2/migrations/) и [restore](../../deploy/00_restore.sh). Ниже все 35 таблиц public, 10 aurelius_cabinet и 1 aurelius_deploy. Колонки, типы, nullable и ограничения извлечены из этих файлов; это справочник структуры, не снимок работающей БД.

## Единицы, происхождение и связи

PK/FK/UNIQUE/CHECK приведены SQL без изменения смысла. Тип numeric сам по себе не доказывает денежную единицу или процентную шкалу. Для неоднозначных полей это отмечено; перед новым адаптером требуется контракт единиц. Nullable означает допустимость NULL по DDL с учётом PRIMARY KEY; условную обязательность анкеты определяют application_field_requirements и сервер. JSON-колонка не означает свободный ввод без бизнес-проверок.

Центральные связи: companies → credit_applications → поля/дозапросы/снимки/решения/офферы; companies → операции/отчётность/обязательства → repayment_history; credit_products → terms → варианты/правила. Служебные FK связывают сессию с user_accounts, состояние с заявкой, публикацию с оффером/расчётом/решением. Точные составные ключи приведены ниже.

## Начальный дамп и изменения после запуска

manifest.created_for_date=2026-10-26: 30 компаний, 32 учётки, 30 исторических заявок, 99 требований, 780 операций. Это начальные числа, не текущие SELECT COUNT. v4 добавляет 60 явно синтетических REVENUE за сентябрь–октябрь 2025 по 1200000 RUB на компанию/месяц. После init появляются служебные таблицы; после сценариев меняются заявки, поля, receipts, события и расчёты. Исторические результаты AUR-01–10 и недоступный прогон 30 заявок не определяют текущие числа строк.

## public

### public.application_data_requests

Дозапросы: вопрос по полю, ответ и состояние запроса. Cabinet.review/answer читает и пишет.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `request_id` | `bigint` | нет | `IDENTITY` | Идентификатор request_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `field_code` | `text` | нет | `—` | Код поля анкеты; текст/код либо величина по контракту поля |
| `question_text` | `text` | нет | `—` | Вопрос сотрудника; текст/код либо величина по контракту поля |
| `request_status` | `character varying(20)` | нет | `'OPEN'::character varying` | Состояние дозапроса; текст/код либо величина по контракту поля |
| `requested_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент requested_at; дата/время PostgreSQL; with time zone — момент времени |
| `answered_at` | `timestamp with time zone` | да | `—` | Момент answered_at; дата/время PostgreSQL; with time zone — момент времени |
| `answer_value` | `jsonb` | да | `—` | Ответ клиента; структура JSON; контракт задаёт потребитель |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_data_requests_request_status_check CHECK (((request_status)::text = ANY (ARRAY[('OPEN'::character varying)::text, ('ANSWERED'::character varying)::text, ('CANCELLED'::character varying)::text])));
CONSTRAINT application_data_requests_pkey PRIMARY KEY (request_id);
CONSTRAINT application_data_requests_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT fk_request_defined_field FOREIGN KEY (product_code, field_code) REFERENCES public.application_field_requirements(product_code, field_code);
CONSTRAINT fk_request_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_data_requests_app_status ON public.application_data_requests USING btree (application_id, request_status);
CREATE INDEX idx_requests_defined_field ON public.application_data_requests USING btree (product_code, field_code);
```

### public.application_details

Контакт, подписант и дополнительные сведения анкеты. Cabinet.save читает и пишет; скоринг читает при построении снимка.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `guarantor_participation` | `boolean` | да | `—` | Участие поручителя; логический признак |
| `proposed_collateral` | `boolean` | да | `—` | Предложенное обеспечение; логический признак |
| `contact_full_name` | `text` | да | `—` | ФИО контакта заявки; текст/код либо величина по контракту поля |
| `contact_role` | `text` | да | `—` | Роль контакта; текст/код либо величина по контракту поля |
| `contact_phone` | `text` | да | `—` | Телефон контакта заявки; текст/код либо величина по контракту поля |
| `signer_full_name` | `text` | да | `—` | ФИО подписанта; текст/код либо величина по контракту поля |
| `signer_authority_basis` | `text` | да | `—` | Основание полномочий подписанта; текст/код либо величина по контракту поля |
| `confirmation_version` | `text` | да | `—` | Версия подтверждения; текст/код либо величина по контракту поля |
| `confirmed_at` | `timestamp with time zone` | да | `—` | Момент confirmed_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_details_pkey PRIMARY KEY (application_id);
CONSTRAINT application_details_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
```

### public.application_field_history

Неизменяемая история значений полей. Пишет триггер aurelius_log_field_change; кабинет/аудитор читает историю.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `history_id` | `bigint` | нет | `IDENTITY` | Идентификатор history_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `field_code` | `text` | нет | `—` | Код поля анкеты; текст/код либо величина по контракту поля |
| `old_value` | `jsonb` | да | `—` | Прежнее значение; структура JSON; контракт задаёт потребитель |
| `new_value` | `jsonb` | да | `—` | Новое значение; структура JSON; контракт задаёт потребитель |
| `changed_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент changed_at; дата/время PostgreSQL; with time zone — момент времени |
| `changed_by_type` | `character varying(20)` | нет | `—` | Тип автора изменения; текст/код либо величина по контракту поля |
| `source_type` | `character varying(20)` | нет | `—` | Тип источника; текст/код либо величина по контракту поля |
| `source_reference` | `text` | да | `—` | Ссылка на источник; текст/код либо величина по контракту поля |
| `verification_status` | `character varying(20)` | нет | `'UNVERIFIED'::character varying` | Состояние проверки; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_field_history_changed_by_type_check CHECK (((changed_by_type)::text = ANY (ARRAY[('CLIENT'::character varying)::text, ('BANK'::character varying)::text, ('SYSTEM'::character varying)::text, ('LLM'::character varying)::text])));
CONSTRAINT application_field_history_source_type_check CHECK (((source_type)::text = ANY (ARRAY[('BANK'::character varying)::text, ('FNS'::character varying)::text, ('SME_REGISTER'::character varying)::text, ('BKI'::character varying)::text, ('CLIENT'::character varying)::text, ('CALCULATED'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT application_field_history_verification_status_check CHECK (((verification_status)::text = ANY (ARRAY[('VERIFIED'::character varying)::text, ('UNVERIFIED'::character varying)::text, ('CONFLICT'::character varying)::text, ('EXPIRED'::character varying)::text])));
CONSTRAINT application_field_history_pkey PRIMARY KEY (history_id);
CONSTRAINT fk_history_defined_field FOREIGN KEY (product_code, field_code) REFERENCES public.application_field_requirements(product_code, field_code);
CONSTRAINT fk_history_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_field_history_application_time ON public.application_field_history USING btree (application_id, changed_at DESC);
CREATE TRIGGER trg_immutable_application_field_history BEFORE DELETE OR UPDATE ON public.application_field_history FOR EACH ROW EXECUTE FUNCTION public.aurelius_reject_history_mutation();
```

### public.application_field_requirements

Требования к полям R01–R03 и форме бизнеса. Seed поставляет; кабинет и ассистент читают, runtime не редактирует справочник.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `field_number` | `integer` | нет | `—` | Порядок поля; идентификатор / номер |
| `field_code` | `text` | нет | `—` | Код поля анкеты; текст/код либо величина по контракту поля |
| `field_label` | `text` | нет | `—` | Название поля; текст/код либо величина по контракту поля |
| `required_ip` | `boolean` | нет | `—` | Обязательно для ИП; логический признак |
| `required_ooo` | `boolean` | нет | `—` | Обязательно для юрлица; логический признак |
| `format_rule` | `text` | да | `—` | Правило формата; текст/код либо величина по контракту поля |
| `source_description` | `text` | да | `—` | Описание источника; текст/код либо величина по контракту поля |
| `fill_method` | `text` | да | `—` | Способ заполнения; текст/код либо величина по контракту поля |
| `target_db_field` | `text` | нет | `—` | Целевое поле данных; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_field_requirements_pkey PRIMARY KEY (product_code, field_number);
CONSTRAINT application_field_requirements_product_code_field_code_key UNIQUE (product_code, field_code);
CONSTRAINT uq_field_product UNIQUE (product_code, field_code);
CONSTRAINT application_field_requirements_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);
```

### public.application_field_values

Значения анкеты с источником и статусом проверки. Cabinet.save/confirm_facts пишет; кабинет и скоринг читают.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `field_code` | `text` | нет | `—` | Код поля анкеты; текст/код либо величина по контракту поля |
| `field_value` | `jsonb` | да | `—` | Текущее значение; структура JSON; контракт задаёт потребитель |
| `value_source` | `character varying(20)` | да | `—` | Источник значения; текст/код либо величина по контракту поля |
| `source_reference` | `text` | да | `—` | Ссылка на источник; текст/код либо величина по контракту поля |
| `obtained_at` | `timestamp with time zone` | да | `—` | Момент obtained_at; дата/время PostgreSQL; with time zone — момент времени |
| `verification_status` | `character varying(20)` | да | `—` | Состояние проверки; текст/код либо величина по контракту поля |
| `updated_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент updated_at; дата/время PostgreSQL; with time zone — момент времени |
| `changed_by_type` | `character varying(20)` | нет | `'SYSTEM'::character varying` | Тип автора изменения; текст/код либо величина по контракту поля |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_field_values_changed_by_type_check CHECK (((changed_by_type)::text = ANY (ARRAY[('CLIENT'::character varying)::text, ('BANK'::character varying)::text, ('SYSTEM'::character varying)::text, ('LLM'::character varying)::text])));
CONSTRAINT application_field_values_value_source_check CHECK (((value_source IS NULL) OR ((value_source)::text = ANY (ARRAY[('BANK'::character varying)::text, ('FNS'::character varying)::text, ('SME_REGISTER'::character varying)::text, ('BKI'::character varying)::text, ('CLIENT'::character varying)::text, ('CALCULATED'::character varying)::text, ('OTHER'::character varying)::text]))));
CONSTRAINT application_field_values_verification_status_check CHECK (((verification_status IS NULL) OR ((verification_status)::text = ANY (ARRAY[('VERIFIED'::character varying)::text, ('UNVERIFIED'::character varying)::text, ('CONFLICT'::character varying)::text, ('EXPIRED'::character varying)::text]))));
CONSTRAINT application_field_values_pkey PRIMARY KEY (application_id, field_code);
CONSTRAINT application_field_values_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT fk_value_defined_field FOREIGN KEY (product_code, field_code) REFERENCES public.application_field_requirements(product_code, field_code);
CONSTRAINT fk_value_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_field_values_product_field ON public.application_field_values USING btree (product_code, field_code);
CREATE TRIGGER trg_log_application_field_values AFTER INSERT OR DELETE OR UPDATE ON public.application_field_values FOR EACH ROW EXECUTE FUNCTION public.aurelius_log_field_change();
```

### public.application_product_details

Параметры линии/овердрафта и траншей. Cabinet.save пишет; библиотека и кабинет читают.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `max_tranche_term_value` | `integer` | да | `—` | Максимальный срок транша; единица указана соседним *_unit |
| `max_tranche_term_unit` | `character varying(10)` | да | `—` | Единица срока транша; код единицы из CHECK |
| `drawdown_start_date` | `date` | да | `—` | Начало выборки; календарная дата |
| `drawdown_end_date` | `date` | да | `—` | Конец выборки; календарная дата |
| `drawdown_period_months` | `integer` | да | `—` | Период выборки; месяцы |
| `is_revolving` | `boolean` | да | `—` | Возобновляемость; логический признак |
| `overdraft_bank_account_id` | `bigint` | да | `—` | Идентификатор overdraft_bank_account_id; идентификатор / номер |
| `overdraft_account_ref` | `character varying(20)` | да | `—` | Счёт овердрафта; текст/код либо величина по контракту поля |
| `overdraft_bank_name` | `text` | да | `—` | Банк овердрафта; текст/код либо величина по контракту поля |
| `overdraft_bank_bik` | `character varying(9)` | да | `—` | БИК банка овердрафта; текст/код либо величина по контракту поля |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_product_details_check CHECK (((drawdown_start_date IS NULL) OR (drawdown_end_date IS NULL) OR (drawdown_end_date >= drawdown_start_date)));
CONSTRAINT application_product_details_drawdown_period_months_check CHECK (((drawdown_period_months IS NULL) OR (drawdown_period_months > 0)));
CONSTRAINT application_product_details_max_tranche_term_unit_check CHECK (((max_tranche_term_unit IS NULL) OR ((max_tranche_term_unit)::text = ANY (ARRAY[('DAYS'::character varying)::text, ('MONTHS'::character varying)::text]))));
CONSTRAINT application_product_details_max_tranche_term_value_check CHECK (((max_tranche_term_value IS NULL) OR (max_tranche_term_value > 0)));
CONSTRAINT application_product_details_overdraft_account_ref_check CHECK (((overdraft_account_ref IS NULL) OR ((overdraft_account_ref)::text ~ '^[0-9]{20}$'::text)));
CONSTRAINT application_product_details_overdraft_bank_bik_check CHECK (((overdraft_bank_bik IS NULL) OR ((overdraft_bank_bik)::text ~ '^[0-9]{9}$'::text)));
CONSTRAINT application_product_details_pkey PRIMARY KEY (application_id);
CONSTRAINT application_product_details_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT fk_details_bank_account_owner FOREIGN KEY (overdraft_bank_account_id, company_id) REFERENCES public.company_bank_accounts(account_id, company_id);
CONSTRAINT fk_details_same_company FOREIGN KEY (application_id, company_id) REFERENCES public.credit_applications(application_id, company_id);
```

### public.application_product_terms

Индивидуальные условия. Скоринг пишет DRAFT; Cabinet.review публикует, accept/staleness меняют статус; клиент читает ограниченную проекцию.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `offer_id` | `bigint` | нет | `IDENTITY` | Идентификатор offer_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `terms_id` | `bigint` | нет | `—` | Идентификатор terms_id; идентификатор / номер |
| `rate_option_id` | `bigint` | да | `—` | Идентификатор rate_option_id; идентификатор / номер |
| `repayment_option_id` | `bigint` | да | `—` | Идентификатор repayment_option_id; идентификатор / номер |
| `offered_amount` | `numeric(18,2)` | да | `—` | Предложенная сумма; деньги; валюта строки, в DEMO RUB |
| `offered_term_months` | `integer` | да | `—` | Срок предложения; месяцы |
| `offered_annual_rate_pct` | `numeric(9,4)` | да | `—` | Годовая ставка предложения; проценты (шкала 0–100); ставка — % годовых |
| `offered_tranche_term_value` | `integer` | да | `—` | Срок транша; единица указана соседним *_unit |
| `offered_tranche_term_unit` | `character varying(10)` | да | `—` | Единица срока транша; код единицы из CHECK |
| `offered_drawdown_period_months` | `integer` | да | `—` | Период выборки; месяцы |
| `offered_service_cost` | `numeric(18,2)` | да | `—` | Стоимость обслуживания; деньги; валюта строки, в DEMO RUB |
| `offered_fees` | `jsonb` | да | `—` | Комиссии предложения; структура JSON; контракт задаёт потребитель |
| `offered_conditions` | `jsonb` | да | `—` | Условия предложения; структура JSON; контракт задаёт потребитель |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `offer_status` | `character varying(20)` | нет | `'DRAFT'::character varying` | Состояние предложения; текст/код либо величина по контракту поля |
| `created_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент created_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_product_terms_offer_status_check CHECK (((offer_status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('PROPOSED'::character varying)::text, ('ACCEPTED'::character varying)::text, ('DECLINED'::character varying)::text])));
CONSTRAINT application_product_terms_offered_amount_check CHECK (((offered_amount IS NULL) OR (offered_amount >= (0)::numeric)));
CONSTRAINT application_product_terms_offered_annual_rate_pct_check CHECK (((offered_annual_rate_pct IS NULL) OR (offered_annual_rate_pct >= (0)::numeric)));
CONSTRAINT application_product_terms_offered_drawdown_period_months_check CHECK (((offered_drawdown_period_months IS NULL) OR (offered_drawdown_period_months > 0)));
CONSTRAINT application_product_terms_offered_service_cost_check CHECK (((offered_service_cost IS NULL) OR (offered_service_cost >= (0)::numeric)));
CONSTRAINT application_product_terms_offered_term_months_check CHECK (((offered_term_months IS NULL) OR (offered_term_months > 0)));
CONSTRAINT application_product_terms_offered_tranche_term_unit_check CHECK (((offered_tranche_term_unit IS NULL) OR ((offered_tranche_term_unit)::text = ANY (ARRAY[('DAYS'::character varying)::text, ('MONTHS'::character varying)::text]))));
CONSTRAINT application_product_terms_offered_tranche_term_value_check CHECK (((offered_tranche_term_value IS NULL) OR (offered_tranche_term_value > 0)));
CONSTRAINT application_product_terms_pkey PRIMARY KEY (offer_id);
CONSTRAINT application_product_terms_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT application_product_terms_rate_option_id_fkey FOREIGN KEY (rate_option_id) REFERENCES public.credit_product_rate_options(rate_option_id);
CONSTRAINT application_product_terms_repayment_option_id_fkey FOREIGN KEY (repayment_option_id) REFERENCES public.credit_product_repayment_options(repayment_option_id);
CONSTRAINT application_product_terms_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);
CONSTRAINT fk_offer_rate_same_terms FOREIGN KEY (rate_option_id, terms_id) REFERENCES public.credit_product_rate_options(rate_option_id, terms_id);
CONSTRAINT fk_offer_repayment_same_terms FOREIGN KEY (repayment_option_id, terms_id) REFERENCES public.credit_product_repayment_options(repayment_option_id, terms_id);
CONSTRAINT fk_offer_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);
CONSTRAINT fk_offer_terms_same_product FOREIGN KEY (terms_id, product_code) REFERENCES public.credit_product_terms(terms_id, product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_offer_application ON public.application_product_terms USING btree (application_id);
CREATE INDEX idx_offer_terms ON public.application_product_terms USING btree (terms_id);
```

### public.application_snapshots

Снимки подачи и расчёта. Пишут кабинет/скоринг; freshness и банковская проекция читают.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `snapshot_id` | `bigint` | нет | `IDENTITY` | Идентификатор snapshot_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `snapshot_type` | `character varying(20)` | нет | `—` | Вид снимка; текст/код либо величина по контракту поля |
| `snapshot_data` | `jsonb` | нет | `—` | Данные снимка; структура JSON; контракт задаёт потребитель |
| `created_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент created_at; дата/время PostgreSQL; with time zone — момент времени |
| `created_by_type` | `character varying(20)` | нет | `—` | Тип создателя; текст/код либо величина по контракту поля |
| `snapshot_version` | `integer` | нет | `—` | Версия снимка; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT application_snapshots_created_by_type_check CHECK (((created_by_type)::text = ANY (ARRAY[('CLIENT'::character varying)::text, ('BANK'::character varying)::text, ('SYSTEM'::character varying)::text, ('LLM'::character varying)::text])));
CONSTRAINT application_snapshots_snapshot_data_check CHECK ((jsonb_typeof(snapshot_data) = 'object'::text));
CONSTRAINT application_snapshots_snapshot_type_check CHECK (((snapshot_type)::text = ANY (ARRAY[('SUBMISSION'::character varying)::text, ('DECISION'::character varying)::text, ('MANUAL'::character varying)::text])));
CONSTRAINT application_snapshots_snapshot_version_check CHECK ((snapshot_version > 0));
CONSTRAINT application_snapshots_application_id_snapshot_version_key UNIQUE (application_id, snapshot_version);
CONSTRAINT application_snapshots_pkey PRIMARY KEY (snapshot_id);
CONSTRAINT application_snapshots_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_snapshots_application_time ON public.application_snapshots USING btree (application_id, created_at DESC);
CREATE TRIGGER trg_immutable_application_snapshots BEFORE DELETE OR UPDATE ON public.application_snapshots FOR EACH ROW EXECUTE FUNCTION public.aurelius_reject_history_mutation();
```

### public.bank_transactions

Синтетические банковские операции. Дамп/seed поставляет; feature_builder читает выручку, кабинет не загружает сюда документы.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `transaction_id` | `bigint` | нет | `IDENTITY` | Идентификатор transaction_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `account_ref` | `character varying(100)` | да | `—` | Ссылка/номер счёта; текст/код либо величина по контракту поля |
| `bank_name` | `character varying(100)` | да | `—` | Наименование банка; текст/код либо величина по контракту поля |
| `transaction_date` | `timestamp with time zone` | нет | `—` | Дата операции; дата/время PostgreSQL; with time zone — момент времени |
| `amount` | `numeric(18,2)` | нет | `—` | Сумма; деньги; валюта строки, в DEMO RUB |
| `currency` | `character(3)` | нет | `'RUB'::bpchar` | Валюта; текст/код либо величина по контракту поля |
| `direction` | `character varying(10)` | нет | `—` | Направление операции; текст/код либо величина по контракту поля |
| `operation_category` | `character varying(30)` | нет | `'UNKNOWN'::character varying` | Категория операции; текст/код либо величина по контракту поля |
| `counterparty_inn` | `character varying(12)` | да | `—` | ИНН контрагента; текст/код либо величина по контракту поля |
| `counterparty_name` | `text` | да | `—` | Наименование контрагента; текст/код либо величина по контракту поля |
| `payment_purpose` | `text` | да | `—` | Назначение платежа; текст/код либо величина по контракту поля |
| `balance_after` | `numeric(18,2)` | да | `—` | Остаток после операции; деньги; валюта строки, в DEMO RUB |
| `source_statement_id` | `character varying(100)` | да | `—` | Идентификатор source_statement_id; идентификатор / номер |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT bank_transactions_amount_check CHECK ((amount >= (0)::numeric));
CONSTRAINT bank_transactions_direction_check CHECK (((direction)::text = ANY (ARRAY[('IN'::character varying)::text, ('OUT'::character varying)::text])));
CONSTRAINT bank_transactions_operation_category_check CHECK (((operation_category)::text = ANY (ARRAY[('REVENUE'::character varying)::text, ('TAX'::character varying)::text, ('PAYROLL'::character varying)::text, ('RENT'::character varying)::text, ('LOAN'::character varying)::text, ('INTERNAL_TRANSFER'::character varying)::text, ('REFUND'::character varying)::text, ('OTHER'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT bank_transactions_pkey PRIMARY KEY (transaction_id);
CONSTRAINT bank_transactions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_bank_transactions_company_date ON public.bank_transactions USING btree (company_id, transaction_date);
```

### public.collateral

Предусмотренное схемой досье залога. Не является подключённым процессом оценки обеспечения; источник наполнения — внешний адаптер/seed, отдельного CRUD в кабинете нет.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `collateral_id` | `bigint` | нет | `IDENTITY` | Идентификатор collateral_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `asset_type` | `character varying(20)` | нет | `—` | Тип обеспечения; текст/код либо величина по контракту поля |
| `asset_description` | `text` | да | `—` | Описание актива; текст/код либо величина по контракту поля |
| `owner_type` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Тип владельца; текст/код либо величина по контракту поля |
| `owner_ref` | `text` | да | `—` | Ссылка на владельца; текст/код либо величина по контракту поля |
| `estimated_market_value` | `numeric(18,2)` | да | `—` | Оценочная рыночная стоимость; текст/код либо величина по контракту поля |
| `valuation_date` | `date` | да | `—` | Дата оценки; календарная дата |
| `discount_rate` | `numeric(6,4)` | да | `—` | Дисконт оценки; семантика определяется кодом показателя/потребителем; DDL единицу не закрепляет |
| `estimated_liquidation_value` | `numeric(18,2)` | да | `—` | Оценочная ликвидационная стоимость; текст/код либо величина по контракту поля |
| `encumbrance_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Обременения; текст/код либо величина по контракту поля |
| `registry_name` | `character varying(50)` | да | `—` | Реестр; текст/код либо величина по контракту поля |
| `registry_record_id` | `text` | да | `—` | Идентификатор записи реестра; идентификатор / номер |
| `verification_date` | `timestamp with time zone` | да | `—` | Дата проверки; дата/время PostgreSQL; with time zone — момент времени |
| `collateral_status` | `character varying(20)` | нет | `'PENDING'::character varying` | Состояние залога; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT collateral_asset_type_check CHECK (((asset_type)::text = ANY (ARRAY[('REAL_ESTATE'::character varying)::text, ('VEHICLE'::character varying)::text, ('EQUIPMENT'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT collateral_collateral_status_check CHECK (((collateral_status)::text = ANY (ARRAY[('PENDING'::character varying)::text, ('VERIFIED'::character varying)::text, ('REJECTED'::character varying)::text, ('RELEASED'::character varying)::text])));
CONSTRAINT collateral_discount_rate_check CHECK (((discount_rate IS NULL) OR ((discount_rate >= (0)::numeric) AND (discount_rate <= (1)::numeric))));
CONSTRAINT collateral_encumbrance_status_check CHECK (((encumbrance_status)::text = ANY (ARRAY[('NONE'::character varying)::text, ('PRESENT'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT collateral_estimated_liquidation_value_check CHECK (((estimated_liquidation_value IS NULL) OR (estimated_liquidation_value >= (0)::numeric)));
CONSTRAINT collateral_estimated_market_value_check CHECK (((estimated_market_value IS NULL) OR (estimated_market_value >= (0)::numeric)));
CONSTRAINT collateral_owner_type_check CHECK (((owner_type)::text = ANY (ARRAY[('COMPANY'::character varying)::text, ('OWNER'::character varying)::text, ('THIRD_PARTY'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT collateral_pkey PRIMARY KEY (collateral_id);
CONSTRAINT collateral_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT collateral_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
CONSTRAINT fk_collateral_same_company FOREIGN KEY (application_id, company_id) REFERENCES public.credit_applications(application_id, company_id);
```

### public.companies

Профиль компании. Seed поставляет; кабинет и скоринг читают. Изменения клиентской анкеты и verify его не исправляют.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `company_id` | `bigint` | нет | `IDENTITY` | Идентификатор company_id; идентификатор / номер |
| `entity_type` | `character varying(30)` | нет | `—` | Тип субъекта; текст/код либо величина по контракту поля |
| `inn` | `character varying(12)` | да | `—` | ИНН; текст/код либо величина по контракту поля |
| `ogrn` | `character varying(13)` | да | `—` | ОГРН; текст/код либо величина по контракту поля |
| `ogrnip` | `character varying(15)` | да | `—` | ОГРНИП; текст/код либо величина по контракту поля |
| `name` | `text` | да | `—` | Наименование; текст/код либо величина по контракту поля |
| `registration_date` | `date` | да | `—` | Дата государственной регистрации; календарная дата |
| `status` | `character varying(30)` | нет | `'UNKNOWN'::character varying` | Состояние записи/компании; текст/код либо величина по контракту поля |
| `status_date` | `date` | да | `—` | Дата состояния; календарная дата |
| `okved_main` | `character varying(10)` | да | `—` | Основной ОКВЭД; текст/код либо величина по контракту поля |
| `region_code` | `character varying(10)` | да | `—` | Код региона; текст/код либо величина по контракту поля |
| `legal_address` | `text` | да | `—` | Юридический адрес; текст/код либо величина по контракту поля |
| `director_name` | `text` | да | `—` | ФИО руководителя; текст/код либо величина по контракту поля |
| `director_authority_confirmed` | `boolean` | да | `—` | Подтверждение полномочий; логический признак |
| `information_reliability_status` | `character varying(30)` | нет | `'UNKNOWN'::character varying` | Достоверность профиля; текст/код либо величина по контракту поля |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |
| `created_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент created_at; дата/время PostgreSQL; with time zone — момент времени |
| `updated_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент updated_at; дата/время PostgreSQL; with time zone — момент времени |
| `kpp` | `character varying(9)` | да | `—` | КПП; текст/код либо величина по контракту поля |
| `legal_form` | `text` | да | `—` | Правовая форма; текст/код либо величина по контракту поля |
| `okved_main_name` | `text` | да | `—` | Наименование ОКВЭД; текст/код либо величина по контракту поля |
| `actual_activity_description` | `text` | да | `—` | Фактическая деятельность; текст/код либо величина по контракту поля |
| `actual_business_address` | `text` | да | `—` | Адрес деятельности; текст/код либо величина по контракту поля |
| `business_region` | `text` | да | `—` | Регион бизнеса; текст/код либо величина по контракту поля |
| `business_city` | `text` | да | `—` | Город бизнеса; текст/код либо величина по контракту поля |
| `sme_category` | `character varying(20)` | да | `—` | Категория МСП; текст/код либо величина по контракту поля |
| `actual_activity_start_date` | `date` | да | `—` | Начало фактической деятельности; календарная дата |
| `director_position` | `text` | да | `—` | Должность руководителя; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT companies_check CHECK (((((entity_type)::text = 'LEGAL_ENTITY'::text) AND (ogrnip IS NULL) AND ((inn IS NULL) OR (length((inn)::text) = 10))) OR (((entity_type)::text = 'INDIVIDUAL_ENTREPRENEUR'::text) AND (ogrn IS NULL) AND ((inn IS NULL) OR (length((inn)::text) = 12)))));
CONSTRAINT companies_entity_type_check CHECK (((entity_type)::text = ANY (ARRAY[('LEGAL_ENTITY'::character varying)::text, ('INDIVIDUAL_ENTREPRENEUR'::character varying)::text])));
CONSTRAINT companies_information_reliability_status_check CHECK (((information_reliability_status)::text = ANY (ARRAY[('VERIFIED'::character varying)::text, ('UNVERIFIED'::character varying)::text, ('CONFLICT'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT companies_inn_check CHECK ((((inn)::text ~ '^[0-9]{10}$'::text) OR ((inn)::text ~ '^[0-9]{12}$'::text)));
CONSTRAINT companies_ogrn_check CHECK (((ogrn IS NULL) OR ((ogrn)::text ~ '^[0-9]{13}$'::text)));
CONSTRAINT companies_ogrnip_check CHECK (((ogrnip IS NULL) OR ((ogrnip)::text ~ '^[0-9]{15}$'::text)));
CONSTRAINT companies_status_check CHECK (((status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('LIQUIDATING'::character varying)::text, ('INACTIVE'::character varying)::text, ('BANKRUPTCY'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT companies_inn_key UNIQUE (inn);
CONSTRAINT companies_pkey PRIMARY KEY (company_id);
```

### public.company_bank_accounts

Счета компании. Справочная структура v4, без отдельного CRUD кабинета; данные должен поставлять адаптер/seed.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `account_id` | `bigint` | нет | `IDENTITY` | Идентификатор account_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `account_number` | `character varying(20)` | нет | `—` | Номер банковского счёта; текст/код либо величина по контракту поля |
| `bank_name` | `text` | нет | `—` | Наименование банка; текст/код либо величина по контракту поля |
| `bank_bik` | `character varying(9)` | да | `—` | БИК банка; текст/код либо величина по контракту поля |
| `account_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Состояние счёта; текст/код либо величина по контракту поля |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT company_bank_accounts_account_number_check CHECK (((account_number)::text ~ '^[0-9]{20}$'::text));
CONSTRAINT company_bank_accounts_account_status_check CHECK (((account_status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('CLOSED'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT company_bank_accounts_bank_bik_check CHECK (((bank_bik IS NULL) OR ((bank_bik)::text ~ '^[0-9]{9}$'::text)));
CONSTRAINT company_bank_accounts_company_id_account_number_key UNIQUE (company_id, account_number);
CONSTRAINT company_bank_accounts_pkey PRIMARY KEY (account_id);
CONSTRAINT uq_account_company UNIQUE (account_id, company_id);
CONSTRAINT company_bank_accounts_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_bank_accounts_company ON public.company_bank_accounts USING btree (company_id);
```

### public.company_contacts

Контакты компании. Справочная структура v4, не отдельный рабочий процесс полномочий.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `contact_id` | `bigint` | нет | `IDENTITY` | Идентификатор contact_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `full_name` | `text` | нет | `—` | ФИО контакта; текст/код либо величина по контракту поля |
| `contact_role` | `text` | да | `—` | Роль контакта; текст/код либо величина по контракту поля |
| `phone` | `text` | да | `—` | Телефон; текст/код либо величина по контракту поля |
| `authority_basis` | `text` | да | `—` | Основание полномочий; текст/код либо величина по контракту поля |
| `is_current` | `boolean` | да | `—` | Актуальность контакта; логический признак |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT company_contacts_pkey PRIMARY KEY (contact_id);
CONSTRAINT company_contacts_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_company_contacts_company ON public.company_contacts USING btree (company_id);
```

### public.company_data_provenance

Происхождение отдельных полей компании. Структура для источников; не следует считать её автоматически заполненным lineage всех данных.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `provenance_id` | `bigint` | нет | `IDENTITY` | Идентификатор provenance_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `target_table` | `text` | нет | `—` | Таблица факта; текст/код либо величина по контракту поля |
| `target_record_pk` | `jsonb` | нет | `—` | Ключ записи факта; идентификатор / номер |
| `target_field` | `text` | нет | `—` | Поле факта; текст/код либо величина по контракту поля |
| `observed_value` | `jsonb` | да | `—` | Наблюдаемое значение; структура JSON; контракт задаёт потребитель |
| `source_type` | `character varying(30)` | нет | `—` | Тип источника; текст/код либо величина по контракту поля |
| `source_reference` | `text` | да | `—` | Ссылка на источник; текст/код либо величина по контракту поля |
| `obtained_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент obtained_at; дата/время PostgreSQL; with time zone — момент времени |
| `verification_status` | `character varying(20)` | нет | `'UNVERIFIED'::character varying` | Состояние проверки; текст/код либо величина по контракту поля |
| `verified_at` | `timestamp with time zone` | да | `—` | Момент verified_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT company_data_provenance_source_type_check CHECK (((source_type)::text = ANY (ARRAY[('BANK'::character varying)::text, ('FNS'::character varying)::text, ('SME_REGISTER'::character varying)::text, ('BKI'::character varying)::text, ('CLIENT'::character varying)::text, ('CALCULATED'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT company_data_provenance_target_record_pk_check CHECK ((jsonb_typeof(target_record_pk) = 'object'::text));
CONSTRAINT company_data_provenance_verification_status_check CHECK (((verification_status)::text = ANY (ARRAY[('VERIFIED'::character varying)::text, ('UNVERIFIED'::character varying)::text, ('CONFLICT'::character varying)::text, ('EXPIRED'::character varying)::text])));
CONSTRAINT company_data_provenance_pkey PRIMARY KEY (provenance_id);
CONSTRAINT company_data_provenance_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_provenance_company_field ON public.company_data_provenance USING btree (company_id, target_table, target_field);
```

### public.credit_applications

Центральная заявка. Cabinet создаёт и меняет состояние; скоринг читает, но не одобряет.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `application_id` | `bigint` | нет | `IDENTITY` | Идентификатор application_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `application_date` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Поле application_date по контракту источника; дата/время PostgreSQL; with time zone — момент времени |
| `requested_amount` | `numeric(18,2)` | да | `—` | Запрошенная сумма; деньги; валюта строки, в DEMO RUB |
| `requested_term_days` | `integer` | да | `—` | Запрошенный срок; дни |
| `purpose` | `text` | да | `—` | Цель финансирования; текст/код либо величина по контракту поля |
| `requested_monthly_payment` | `numeric(18,2)` | да | `—` | Заявленный месячный платёж; деньги; валюта строки, в DEMO RUB |
| `application_status` | `character varying(20)` | нет | `'DRAFT'::character varying` | Состояние заявки; текст/код либо величина по контракту поля |
| `missing_data_status` | `character varying(20)` | нет | `'PARTIAL'::character varying` | Полнота данных; текст/код либо величина по контракту поля |
| `decision_date` | `timestamp with time zone` | да | `—` | Поле decision_date по контракту источника; дата/время PostgreSQL; with time zone — момент времени |
| `requested_data_deadline` | `timestamp with time zone` | да | `—` | Поле requested_data_deadline по контракту источника; дата/время PostgreSQL; with time zone — момент времени |
| `requested_term_months` | `integer` | да | `—` | Запрошенный срок; месяцы |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_applications_application_status_check CHECK (((application_status)::text = ANY (ARRAY[('DRAFT'::character varying)::text, ('SUBMITTED'::character varying)::text, ('UNDER_REVIEW'::character varying)::text, ('AWAITING_DATA'::character varying)::text, ('APPROVED'::character varying)::text, ('REJECTED'::character varying)::text, ('CANCELLED'::character varying)::text])));
CONSTRAINT credit_applications_missing_data_status_check CHECK (((missing_data_status)::text = ANY (ARRAY[('COMPLETE'::character varying)::text, ('PARTIAL'::character varying)::text, ('CRITICAL_MISSING'::character varying)::text])));
CONSTRAINT credit_applications_requested_amount_check CHECK (((requested_amount IS NULL) OR (requested_amount > (0)::numeric)));
CONSTRAINT credit_applications_requested_monthly_payment_check CHECK (((requested_monthly_payment IS NULL) OR (requested_monthly_payment >= (0)::numeric)));
CONSTRAINT credit_applications_requested_term_days_check CHECK (((requested_term_days IS NULL) OR (requested_term_days > 0)));
CONSTRAINT credit_applications_pkey PRIMARY KEY (application_id);
CONSTRAINT uq_application_company UNIQUE (application_id, company_id);
CONSTRAINT uq_application_company_product UNIQUE (application_id, company_id, product_code);
CONSTRAINT uq_application_product UNIQUE (application_id, product_code);
CONSTRAINT credit_applications_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
CONSTRAINT credit_applications_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_applications_company_date ON public.credit_applications USING btree (company_id, application_date);
```

### public.credit_decisions

Неизменяемые результаты расчёта и решения сотрудника. Пишут scoring persistence и Cabinet.review; кабинет выбирает последнее релевантное решение.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `decision_id` | `bigint` | нет | `IDENTITY` | Идентификатор decision_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `scoring_result_id` | `bigint` | да | `—` | Идентификатор scoring_result_id; идентификатор / номер |
| `policy_version` | `character varying(50)` | нет | `—` | Версия политики; текст/код либо величина по контракту поля |
| `decided_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент decided_at; дата/время PostgreSQL; with time zone — момент времени |
| `eligibility_status` | `character varying(20)` | нет | `—` | Допуск/полнота; текст/код либо величина по контракту поля |
| `decision` | `character varying(20)` | нет | `—` | Решение; текст/код либо величина по контракту поля |
| `approved_amount` | `numeric(18,2)` | да | `—` | Одобренная сумма; деньги; валюта строки, в DEMO RUB |
| `approved_term_days` | `integer` | да | `—` | Одобренный срок; дни |
| `reasons` | `jsonb` | да | `—` | Причины решения; структура JSON; контракт задаёт потребитель |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_decisions_approved_amount_check CHECK (((approved_amount IS NULL) OR (approved_amount >= (0)::numeric)));
CONSTRAINT credit_decisions_approved_term_days_check CHECK (((approved_term_days IS NULL) OR (approved_term_days >= 0)));
CONSTRAINT credit_decisions_decision_check CHECK (((decision)::text = ANY (ARRAY[('APPROVE'::character varying)::text, ('REJECT'::character varying)::text, ('REQUEST_DATA'::character varying)::text, ('MANUAL_REVIEW'::character varying)::text])));
CONSTRAINT credit_decisions_eligibility_status_check CHECK (((eligibility_status)::text = ANY (ARRAY[('ELIGIBLE'::character varying)::text, ('INELIGIBLE'::character varying)::text, ('NEEDS_DATA'::character varying)::text])));
CONSTRAINT credit_decisions_pkey PRIMARY KEY (decision_id);
CONSTRAINT credit_decisions_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT credit_decisions_scoring_result_id_fkey FOREIGN KEY (scoring_result_id) REFERENCES public.scoring_results(scoring_result_id);
CONSTRAINT fk_decision_scoring_same_application FOREIGN KEY (scoring_result_id, application_id) REFERENCES public.scoring_results(scoring_result_id, application_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_credit_decisions_application_date ON public.credit_decisions USING btree (application_id, decided_at);
CREATE INDEX idx_decisions_scoring ON public.credit_decisions USING btree (scoring_result_id, application_id);
```

### public.credit_history_events

События кредитной истории. Таблица источника v4; наличие схемы не означает живой коннектор БКИ.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `event_id` | `bigint` | нет | `IDENTITY` | Идентификатор event_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `obligation_id` | `bigint` | да | `—` | Идентификатор obligation_id; идентификатор / номер |
| `event_type` | `character varying(20)` | нет | `—` | Вид события; текст/код либо величина по контракту поля |
| `event_date` | `date` | нет | `—` | Дата события; календарная дата |
| `overdue_days` | `integer` | да | `—` | Длительность просрочки; дни |
| `overdue_amount` | `numeric(18,2)` | да | `—` | Просроченная сумма; деньги; валюта строки, в DEMO RUB |
| `resolution_date` | `date` | да | `—` | Дата разрешения события; календарная дата |
| `event_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Состояние события; текст/код либо величина по контракту поля |
| `source_event_id` | `text` | да | `—` | Идентификатор source_event_id; идентификатор / номер |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_history_events_check CHECK (((resolution_date IS NULL) OR (resolution_date >= event_date)));
CONSTRAINT credit_history_events_event_status_check CHECK (((event_status)::text = ANY (ARRAY[('OPEN'::character varying)::text, ('RESOLVED'::character varying)::text, ('IN_PROGRESS'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT credit_history_events_event_type_check CHECK (((event_type)::text = ANY (ARRAY[('DELINQUENCY'::character varying)::text, ('RESTRUCTURING'::character varying)::text, ('DEFAULT'::character varying)::text, ('WRITE_OFF'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT credit_history_events_overdue_amount_check CHECK (((overdue_amount IS NULL) OR (overdue_amount >= (0)::numeric)));
CONSTRAINT credit_history_events_overdue_days_check CHECK (((overdue_days IS NULL) OR (overdue_days >= 0)));
CONSTRAINT credit_history_events_pkey PRIMARY KEY (event_id);
CONSTRAINT credit_history_events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
CONSTRAINT credit_history_events_obligation_id_fkey FOREIGN KEY (obligation_id) REFERENCES public.credit_obligations(obligation_id);
CONSTRAINT fk_credit_event_same_company FOREIGN KEY (obligation_id, company_id) REFERENCES public.credit_obligations(obligation_id, company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_credit_history_company_date ON public.credit_history_events USING btree (company_id, event_date);
```

### public.credit_line_operations

Операции по линии. Структура v4 для внешнего источника; выдача и обслуживание не реализованы кабинетом.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `operation_id` | `bigint` | нет | `IDENTITY` | Идентификатор operation_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `operation_date` | `timestamp with time zone` | нет | `—` | Дата операции линии; дата/время PostgreSQL; with time zone — момент времени |
| `operation_type` | `character varying(20)` | нет | `—` | Тип операции линии; текст/код либо величина по контракту поля |
| `operation_amount` | `numeric(18,2)` | нет | `—` | Сумма операции линии; деньги; валюта строки, в DEMO RUB |
| `credit_limit` | `numeric(18,2)` | да | `—` | Кредитный лимит; деньги; валюта строки, в DEMO RUB |
| `outstanding_debt` | `numeric(18,2)` | да | `—` | Текущий долг; деньги; валюта строки, в DEMO RUB |
| `available_limit` | `numeric(18,2)` | да | `—` | Свободный лимит; деньги; валюта строки, в DEMO RUB |
| `source_operation_id` | `text` | да | `—` | Идентификатор source_operation_id; идентификатор / номер |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_line_operations_available_limit_check CHECK (((available_limit IS NULL) OR (available_limit >= (0)::numeric)));
CONSTRAINT credit_line_operations_credit_limit_check CHECK (((credit_limit IS NULL) OR (credit_limit >= (0)::numeric)));
CONSTRAINT credit_line_operations_operation_amount_check CHECK ((operation_amount >= (0)::numeric));
CONSTRAINT credit_line_operations_operation_type_check CHECK (((operation_type)::text = ANY (ARRAY[('DRAWDOWN'::character varying)::text, ('REPAYMENT'::character varying)::text, ('LIMIT_CHANGE'::character varying)::text, ('INTEREST'::character varying)::text])));
CONSTRAINT credit_line_operations_outstanding_debt_check CHECK (((outstanding_debt IS NULL) OR (outstanding_debt >= (0)::numeric)));
CONSTRAINT credit_line_operations_pkey PRIMARY KEY (operation_id);
CONSTRAINT credit_line_operations_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT credit_line_operations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
CONSTRAINT credit_line_operations_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);
CONSTRAINT fk_line_operation_same_company_product FOREIGN KEY (application_id, company_id, product_code) REFERENCES public.credit_applications(application_id, company_id, product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_operations_application ON public.credit_line_operations USING btree (application_id);
```

### public.credit_obligations

Известные обязательства и платежная нагрузка. Seed/источник пишет; feature_builder читает.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `obligation_id` | `bigint` | нет | `IDENTITY` | Идентификатор obligation_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `creditor_name` | `text` | да | `—` | Кредитор; текст/код либо величина по контракту поля |
| `obligation_type` | `character varying(20)` | нет | `—` | Тип обязательства; текст/код либо величина по контракту поля |
| `contract_ref` | `character varying(100)` | да | `—` | Номер/ссылка договора; текст/код либо величина по контракту поля |
| `contract_date` | `date` | да | `—` | Дата договора; календарная дата |
| `maturity_date` | `date` | да | `—` | Дата погашения; календарная дата |
| `disbursement_date` | `date` | да | `—` | Дата выдачи из источника; календарная дата |
| `actual_close_date` | `date` | да | `—` | Фактическое закрытие; календарная дата |
| `first_default_date` | `date` | да | `—` | Первое событие дефолта из источника; календарная дата |
| `original_amount` | `numeric(18,2)` | да | `—` | Первоначальная сумма; деньги; валюта строки, в DEMO RUB |
| `outstanding_balance` | `numeric(18,2)` | да | `—` | Остаток долга; деньги; валюта строки, в DEMO RUB |
| `monthly_payment` | `numeric(18,2)` | да | `—` | Месячный платёж; деньги; валюта строки, в DEMO RUB |
| `interest_rate` | `numeric(8,4)` | да | `—` | Ставка источника; семантика определяется кодом показателя/потребителем; DDL единицу не закрепляет |
| `overdue_amount` | `numeric(18,2)` | да | `—` | Просроченная сумма; деньги; валюта строки, в DEMO RUB |
| `obligation_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Состояние обязательства; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_obligations_check CHECK (((maturity_date IS NULL) OR (contract_date IS NULL) OR (maturity_date >= contract_date)));
CONSTRAINT credit_obligations_interest_rate_check CHECK (((interest_rate IS NULL) OR (interest_rate >= (0)::numeric)));
CONSTRAINT credit_obligations_monthly_payment_check CHECK (((monthly_payment IS NULL) OR (monthly_payment >= (0)::numeric)));
CONSTRAINT credit_obligations_obligation_status_check CHECK (((obligation_status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('OVERDUE'::character varying)::text, ('RESTRUCTURED'::character varying)::text, ('CLOSED'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT credit_obligations_obligation_type_check CHECK (((obligation_type)::text = ANY (ARRAY[('LOAN'::character varying)::text, ('CREDIT_LINE'::character varying)::text, ('OVERDRAFT'::character varying)::text, ('LEASING'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT credit_obligations_original_amount_check CHECK (((original_amount IS NULL) OR (original_amount >= (0)::numeric)));
CONSTRAINT credit_obligations_outstanding_balance_check CHECK (((outstanding_balance IS NULL) OR (outstanding_balance >= (0)::numeric)));
CONSTRAINT credit_obligations_overdue_amount_check CHECK (((overdue_amount IS NULL) OR (overdue_amount >= (0)::numeric)));
CONSTRAINT credit_obligations_pkey PRIMARY KEY (obligation_id);
CONSTRAINT uq_obligation_company UNIQUE (obligation_id, company_id);
CONSTRAINT credit_obligations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_credit_obligations_company ON public.credit_obligations USING btree (company_id);
```

### public.credit_product_eligibility_rules

Правила допуска продукта. Справочник читает скоринг; редактора правил в кабинете нет.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `rule_id` | `bigint` | нет | `IDENTITY` | Идентификатор rule_id; идентификатор / номер |
| `terms_id` | `bigint` | нет | `—` | Идентификатор terms_id; идентификатор / номер |
| `rule_code` | `text` | нет | `—` | Код правила; текст/код либо величина по контракту поля |
| `rule_description` | `text` | нет | `—` | Описание правила; текст/код либо величина по контракту поля |
| `parameter_name` | `text` | да | `—` | Имя параметра; текст/код либо величина по контракту поля |
| `comparison_operator` | `character varying(10)` | да | `—` | Оператор сравнения; текст/код либо величина по контракту поля |
| `threshold_value` | `jsonb` | да | `—` | Порог правила; семантика определяется кодом показателя/потребителем; DDL единицу не закрепляет |
| `required_data_field` | `text` | да | `—` | Необходимое поле; текст/код либо величина по контракту поля |
| `severity` | `character varying(20)` | нет | `'REVIEW'::character varying` | Критичность; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_product_eligibility_rules_comparison_operator_check CHECK (((comparison_operator IS NULL) OR ((comparison_operator)::text = ANY (ARRAY[('EQ'::character varying)::text, ('NE'::character varying)::text, ('GT'::character varying)::text, ('GTE'::character varying)::text, ('LT'::character varying)::text, ('LTE'::character varying)::text, ('IN'::character varying)::text]))));
CONSTRAINT credit_product_eligibility_rules_severity_check CHECK (((severity)::text = ANY (ARRAY[('BLOCK'::character varying)::text, ('REVIEW'::character varying)::text, ('INFORMATION'::character varying)::text])));
CONSTRAINT credit_product_eligibility_rules_pkey PRIMARY KEY (rule_id);
CONSTRAINT credit_product_eligibility_rules_terms_id_rule_code_key UNIQUE (terms_id, rule_code);
CONSTRAINT credit_product_eligibility_rules_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);
```

### public.credit_product_fees

Комиссии продукта. Читает расчёт условий; источник — справочник, не генерация LLM.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `fee_id` | `bigint` | нет | `IDENTITY` | Идентификатор fee_id; идентификатор / номер |
| `terms_id` | `bigint` | нет | `—` | Идентификатор terms_id; идентификатор / номер |
| `fee_name` | `text` | нет | `—` | Название комиссии; текст/код либо величина по контракту поля |
| `fee_type` | `character varying(30)` | нет | `—` | Тип комиссии; текст/код либо величина по контракту поля |
| `fee_value` | `numeric(18,4)` | да | `—` | Значение комиссии; зависит от fee_type / service_fee_type |
| `fee_frequency` | `text` | да | `—` | Периодичность комиссии; текст/код либо величина по контракту поля |
| `applies_when` | `text` | да | `—` | Условие применения; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_product_fees_fee_type_check CHECK (((fee_type)::text = ANY (ARRAY[('FIXED'::character varying)::text, ('PERCENT_OF_LIMIT'::character varying)::text, ('PERCENT_OF_AMOUNT'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT credit_product_fees_pkey PRIMARY KEY (fee_id);
CONSTRAINT credit_product_fees_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);
```

### public.credit_product_purposes

Допустимые цели. Скоринг читает справочник, runtime не редактирует.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `purpose_id` | `bigint` | нет | `IDENTITY` | Идентификатор purpose_id; идентификатор / номер |
| `terms_id` | `bigint` | нет | `—` | Идентификатор terms_id; идентификатор / номер |
| `purpose_name` | `text` | нет | `—` | Название цели; текст/код либо величина по контракту поля |
| `is_allowed` | `boolean` | нет | `true` | Разрешённость цели; логический признак |
| `restriction_description` | `text` | да | `—` | Ограничение цели; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_product_purposes_pkey PRIMARY KEY (purpose_id);
CONSTRAINT credit_product_purposes_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);
```

### public.credit_product_rate_options

Варианты ставки и обслуживания. Скоринг читает; Cabinet не меняет тарифную политику.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `rate_option_id` | `bigint` | нет | `IDENTITY` | Идентификатор rate_option_id; идентификатор / номер |
| `terms_id` | `bigint` | нет | `—` | Идентификатор terms_id; идентификатор / номер |
| `option_name` | `text` | нет | `—` | Название варианта; текст/код либо величина по контракту поля |
| `min_annual_rate_pct` | `numeric(9,4)` | да | `—` | Нижняя годовая ставка; проценты (шкала 0–100); ставка — % годовых |
| `max_annual_rate_pct` | `numeric(9,4)` | да | `—` | Верхняя годовая ставка; проценты (шкала 0–100); ставка — % годовых |
| `additional_service_name` | `text` | да | `—` | Дополнительная услуга; текст/код либо величина по контракту поля |
| `service_fee_type` | `character varying(30)` | да | `—` | Тип платы за услугу; текст/код либо величина по контракту поля |
| `service_fee_frequency` | `character varying(20)` | да | `—` | Периодичность платы; текст/код либо величина по контракту поля |
| `service_fee_amount` | `numeric(18,4)` | да | `—` | Размер платы; деньги; валюта строки, в DEMO RUB |
| `discount_end_condition` | `text` | да | `—` | Условие окончания скидки; текст/код либо величина по контракту поля |
| `max_tranche_term_days` | `integer` | да | `—` | Максимальный срок транша; дни |
| `limit_review_frequency` | `character varying(30)` | да | `—` | Периодичность пересмотра лимита; текст/код либо величина по контракту поля |
| `limit_reduction_protected` | `boolean` | да | `—` | Защита от снижения лимита; логический признак |
| `service_fee_allowed_pct` | `numeric(6,2)[]` | да | `—` | Допустимая процентная плата; проценты (шкала 0–100); ставка — % годовых |
| `max_tranche_term_months` | `integer` | да | `—` | Максимальный срок транша; месяцы |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_product_rate_options_check CHECK (((max_annual_rate_pct IS NULL) OR (min_annual_rate_pct IS NULL) OR (max_annual_rate_pct >= min_annual_rate_pct)));
CONSTRAINT credit_product_rate_options_max_annual_rate_pct_check CHECK (((max_annual_rate_pct IS NULL) OR (max_annual_rate_pct >= (0)::numeric)));
CONSTRAINT credit_product_rate_options_min_annual_rate_pct_check CHECK (((min_annual_rate_pct IS NULL) OR (min_annual_rate_pct >= (0)::numeric)));
CONSTRAINT credit_product_rate_options_service_fee_amount_check CHECK (((service_fee_amount IS NULL) OR (service_fee_amount >= (0)::numeric)));
CONSTRAINT credit_product_rate_options_service_fee_type_check CHECK (((service_fee_type IS NULL) OR ((service_fee_type)::text = ANY (ARRAY[('FIXED'::character varying)::text, ('PERCENT_OF_LIMIT'::character varying)::text, ('PERCENT_OF_AMOUNT'::character varying)::text, ('OTHER'::character varying)::text]))));
CONSTRAINT credit_product_rate_options_pkey PRIMARY KEY (rate_option_id);
CONSTRAINT credit_product_rate_options_rate_option_id_terms_id_key UNIQUE (rate_option_id, terms_id);
CONSTRAINT credit_product_rate_options_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_rates_terms ON public.credit_product_rate_options USING btree (terms_id);
```

### public.credit_product_repayment_options

Варианты графика. Читает credit_offer; наполняется справочником.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `repayment_option_id` | `bigint` | нет | `IDENTITY` | Идентификатор repayment_option_id; идентификатор / номер |
| `terms_id` | `bigint` | нет | `—` | Идентификатор terms_id; идентификатор / номер |
| `repayment_type` | `character varying(30)` | нет | `—` | Тип графика погашения; текст/код либо величина по контракту поля |
| `principal_payment_frequency` | `character varying(20)` | да | `—` | Периодичность основного долга; текст/код либо величина по контракту поля |
| `interest_payment_frequency` | `character varying(20)` | да | `—` | Периодичность процентов; текст/код либо величина по контракту поля |
| `automatic_from_account` | `boolean` | да | `—` | Автосписание со счёта; логический признак |
| `description` | `text` | да | `—` | Описание; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_product_repayment_options_repayment_type_check CHECK (((repayment_type)::text = ANY (ARRAY[('ANNUITY'::character varying)::text, ('EQUAL_PRINCIPAL'::character varying)::text, ('BULLET'::character varying)::text, ('CASH_SWEEP'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT credit_product_repayment_optio_repayment_option_id_terms_id_key UNIQUE (repayment_option_id, terms_id);
CONSTRAINT credit_product_repayment_options_pkey PRIMARY KEY (repayment_option_id);
CONSTRAINT credit_product_repayment_options_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_repayment_terms ON public.credit_product_repayment_options USING btree (terms_id);
```

### public.credit_product_terms

Версии продуктовых условий с периодом действия. Читают каталог и скоринг; наполняются seed/внешним владельцем справочника.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `terms_id` | `bigint` | нет | `IDENTITY` | Идентификатор terms_id; идентификатор / номер |
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `version_code` | `text` | нет | `—` | Код версии условий; текст/код либо величина по контракту поля |
| `effective_from` | `date` | да | `—` | Начало действия; календарная дата |
| `effective_to` | `date` | да | `—` | Конец действия; календарная дата |
| `min_amount` | `numeric(18,2)` | да | `—` | Минимальная сумма; деньги; валюта строки, в DEMO RUB |
| `max_amount` | `numeric(18,2)` | да | `—` | Максимальная сумма; деньги; валюта строки, в DEMO RUB |
| `min_contract_term_value` | `integer` | да | `—` | Минимальный срок договора; единица указана соседним *_unit |
| `max_contract_term_value` | `integer` | да | `—` | Максимальный срок договора; единица указана соседним *_unit |
| `contract_term_unit` | `character varying(10)` | да | `—` | Единица срока договора; код единицы из CHECK |
| `min_tranche_amount` | `numeric(18,2)` | да | `—` | Минимальная сумма транша; деньги; валюта строки, в DEMO RUB |
| `min_tranche_term_value` | `integer` | да | `—` | Минимальный срок транша; единица указана соседним *_unit |
| `max_tranche_term_value` | `integer` | да | `—` | Максимальный срок транша; единица указана соседним *_unit |
| `tranche_term_unit` | `character varying(10)` | да | `—` | Единица срока транша; код единицы из CHECK |
| `drawdown_period_months` | `integer` | да | `—` | Период выборки; месяцы |
| `drawdown_end_before_maturity_months` | `integer` | да | `—` | Окончание выборки до погашения; месяцы |
| `is_revolving` | `boolean` | да | `—` | Возобновляемость; логический признак |
| `auto_renewal` | `boolean` | да | `—` | Автопродление; логический признак |
| `renewal_period_months` | `integer` | да | `—` | Период продления; месяцы |
| `requires_collateral` | `boolean` | да | `—` | Требуется залог; логический признак |
| `guarantor_requirement` | `character varying(20)` | да | `—` | Требование к поручителю; текст/код либо величина по контракту поля |
| `min_business_age_months` | `integer` | да | `—` | Минимальный возраст бизнеса; месяцы |
| `allowed_entity_types` | `text[]` | да | `—` | Допустимые формы субъекта; текст/код либо величина по контракту поля |
| `allowed_sme_categories` | `text[]` | да | `—` | Допустимые категории МСП; текст/код либо величина по контракту поля |
| `source_url` | `text` | да | `—` | URL источника; текст/код либо величина по контракту поля |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_product_terms_check CHECK (((max_amount IS NULL) OR (min_amount IS NULL) OR (max_amount >= min_amount)));
CONSTRAINT credit_product_terms_check1 CHECK (((effective_to IS NULL) OR (effective_from IS NULL) OR (effective_to >= effective_from)));
CONSTRAINT credit_product_terms_check2 CHECK (((max_contract_term_value IS NULL) OR (min_contract_term_value IS NULL) OR (max_contract_term_value >= min_contract_term_value)));
CONSTRAINT credit_product_terms_check3 CHECK (((max_tranche_term_value IS NULL) OR (min_tranche_term_value IS NULL) OR (max_tranche_term_value >= min_tranche_term_value)));
CONSTRAINT credit_product_terms_check4 CHECK ((((min_contract_term_value IS NULL) AND (max_contract_term_value IS NULL)) OR (contract_term_unit IS NOT NULL)));
CONSTRAINT credit_product_terms_check5 CHECK ((((min_tranche_term_value IS NULL) AND (max_tranche_term_value IS NULL)) OR (tranche_term_unit IS NOT NULL)));
CONSTRAINT credit_product_terms_contract_term_unit_check CHECK (((contract_term_unit IS NULL) OR ((contract_term_unit)::text = ANY (ARRAY[('DAYS'::character varying)::text, ('MONTHS'::character varying)::text]))));
CONSTRAINT credit_product_terms_drawdown_end_before_maturity_months_check CHECK (((drawdown_end_before_maturity_months IS NULL) OR (drawdown_end_before_maturity_months >= 0)));
CONSTRAINT credit_product_terms_drawdown_period_months_check CHECK (((drawdown_period_months IS NULL) OR (drawdown_period_months > 0)));
CONSTRAINT credit_product_terms_guarantor_requirement_check CHECK (((guarantor_requirement IS NULL) OR ((guarantor_requirement)::text = ANY (ARRAY[('REQUIRED'::character varying)::text, ('NOT_REQUIRED'::character varying)::text, ('CONDITIONAL'::character varying)::text, ('UNKNOWN'::character varying)::text]))));
CONSTRAINT credit_product_terms_max_amount_check CHECK (((max_amount IS NULL) OR (max_amount >= (0)::numeric)));
CONSTRAINT credit_product_terms_max_contract_term_value_check CHECK (((max_contract_term_value IS NULL) OR (max_contract_term_value > 0)));
CONSTRAINT credit_product_terms_max_tranche_term_value_check CHECK (((max_tranche_term_value IS NULL) OR (max_tranche_term_value > 0)));
CONSTRAINT credit_product_terms_min_amount_check CHECK (((min_amount IS NULL) OR (min_amount >= (0)::numeric)));
CONSTRAINT credit_product_terms_min_business_age_months_check CHECK (((min_business_age_months IS NULL) OR (min_business_age_months >= 0)));
CONSTRAINT credit_product_terms_min_contract_term_value_check CHECK (((min_contract_term_value IS NULL) OR (min_contract_term_value > 0)));
CONSTRAINT credit_product_terms_min_tranche_amount_check CHECK (((min_tranche_amount IS NULL) OR (min_tranche_amount >= (0)::numeric)));
CONSTRAINT credit_product_terms_min_tranche_term_value_check CHECK (((min_tranche_term_value IS NULL) OR (min_tranche_term_value > 0)));
CONSTRAINT credit_product_terms_renewal_period_months_check CHECK (((renewal_period_months IS NULL) OR (renewal_period_months > 0)));
CONSTRAINT credit_product_terms_tranche_term_unit_check CHECK (((tranche_term_unit IS NULL) OR ((tranche_term_unit)::text = ANY (ARRAY[('DAYS'::character varying)::text, ('MONTHS'::character varying)::text]))));
CONSTRAINT credit_product_terms_pkey PRIMARY KEY (terms_id);
CONSTRAINT credit_product_terms_product_code_version_code_key UNIQUE (product_code, version_code);
CONSTRAINT credit_product_terms_terms_id_product_code_key UNIQUE (terms_id, product_code);
CONSTRAINT credit_product_terms_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_terms_product ON public.credit_product_terms USING btree (product_code);
```

### public.credit_products

Коды и активность продуктов. Читают кабинет/скоринг; в seed R01–R03.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `product_code` | `character varying(10)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `product_name` | `text` | нет | `—` | Наименование продукта; текст/код либо величина по контракту поля |
| `product_type` | `character varying(20)` | нет | `—` | Вид продукта; текст/код либо величина по контракту поля |
| `active` | `boolean` | нет | `true` | Активность продукта; логический признак |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_products_product_type_check CHECK (((product_type)::text = ANY (ARRAY[('TERM_LOAN'::character varying)::text, ('CREDIT_LINE'::character varying)::text, ('OVERDRAFT'::character varying)::text])));
CONSTRAINT credit_products_pkey PRIMARY KEY (product_code);
```

### public.credit_repayment_history

Наблюдения платежей по обязательствам. Читает feature_builder; поставляет seed/источник, не PDF upload.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `repayment_id` | `bigint` | нет | `IDENTITY` | Идентификатор repayment_id; идентификатор / номер |
| `obligation_id` | `bigint` | нет | `—` | Идентификатор obligation_id; идентификатор / номер |
| `period_date` | `date` | нет | `—` | Дата платёжного периода; календарная дата |
| `scheduled_payment` | `numeric(18,2)` | да | `—` | Плановый платёж; деньги; валюта строки, в DEMO RUB |
| `actual_payment` | `numeric(18,2)` | да | `—` | Фактический платёж; деньги; валюта строки, в DEMO RUB |
| `outstanding_balance` | `numeric(18,2)` | да | `—` | Остаток долга; деньги; валюта строки, в DEMO RUB |
| `overdue_amount` | `numeric(18,2)` | да | `—` | Просроченная сумма; деньги; валюта строки, в DEMO RUB |
| `overdue_days` | `integer` | да | `—` | Длительность просрочки; дни |
| `default_flag` | `boolean` | да | `—` | Флаг события дефолта источника; логический признак |
| `observation_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Состояние наблюдения; текст/код либо величина по контракту поля |
| `source_record_id` | `text` | да | `—` | Идентификатор source_record_id; идентификатор / номер |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |
| `created_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент created_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT credit_repayment_history_actual_payment_check CHECK (((actual_payment IS NULL) OR (actual_payment >= (0)::numeric)));
CONSTRAINT credit_repayment_history_observation_status_check CHECK (((observation_status)::text = ANY (ARRAY[('ACTIVE'::character varying)::text, ('CLOSED'::character varying)::text, ('DEFAULT'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT credit_repayment_history_outstanding_balance_check CHECK (((outstanding_balance IS NULL) OR (outstanding_balance >= (0)::numeric)));
CONSTRAINT credit_repayment_history_overdue_amount_check CHECK (((overdue_amount IS NULL) OR (overdue_amount >= (0)::numeric)));
CONSTRAINT credit_repayment_history_overdue_days_check CHECK (((overdue_days IS NULL) OR (overdue_days >= 0)));
CONSTRAINT credit_repayment_history_scheduled_payment_check CHECK (((scheduled_payment IS NULL) OR (scheduled_payment >= (0)::numeric)));
CONSTRAINT credit_repayment_history_obligation_id_period_date_key UNIQUE (obligation_id, period_date);
CONSTRAINT credit_repayment_history_pkey PRIMARY KEY (repayment_id);
CONSTRAINT credit_repayment_history_obligation_id_fkey FOREIGN KEY (obligation_id) REFERENCES public.credit_obligations(obligation_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_repayment_history_default ON public.credit_repayment_history USING btree (obligation_id, period_date) WHERE (default_flag = true);
CREATE INDEX idx_repayment_history_period ON public.credit_repayment_history USING btree (period_date);
```

### public.data_quality_checks

Предусмотренные проверки качества данных. Не заменяют текущий events.verify; отдельного runtime-конвейера заполнения всех проверок не заявлено.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `check_id` | `bigint` | нет | `IDENTITY` | Идентификатор check_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `application_id` | `bigint` | да | `—` | Идентификатор application_id; идентификатор / номер |
| `source_name` | `character varying(50)` | да | `—` | Источник; текст/код либо величина по контракту поля |
| `field_name` | `character varying(100)` | да | `—` | Проверяемое поле; текст/код либо величина по контракту поля |
| `check_type` | `character varying(20)` | нет | `—` | Тип проверки качества; текст/код либо величина по контракту поля |
| `check_status` | `character varying(20)` | нет | `—` | Результат проверки качества; текст/код либо величина по контракту поля |
| `checked_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент checked_at; дата/время PostgreSQL; with time zone — момент времени |
| `data_as_of` | `timestamp with time zone` | да | `—` | Дата актуальности данных; дата/время PostgreSQL; with time zone — момент времени |
| `missing_fields` | `jsonb` | да | `—` | Недостающие поля; структура JSON; контракт задаёт потребитель |
| `conflict_description` | `text` | да | `—` | Описание конфликта; текст/код либо величина по контракту поля |
| `severity` | `character varying(20)` | нет | `'MEDIUM'::character varying` | Критичность; текст/код либо величина по контракту поля |
| `resolution_status` | `character varying(20)` | нет | `'OPEN'::character varying` | Состояние разрешения; текст/код либо величина по контракту поля |
| `resolution_comment` | `text` | да | `—` | Комментарий разрешения; текст/код либо величина по контракту поля |

Ограничения (включая PK/FK):

```sql
CONSTRAINT data_quality_checks_check_status_check CHECK (((check_status)::text = ANY (ARRAY[('PASS'::character varying)::text, ('FAIL'::character varying)::text, ('WARNING'::character varying)::text, ('NOT_CHECKED'::character varying)::text])));
CONSTRAINT data_quality_checks_check_type_check CHECK (((check_type)::text = ANY (ARRAY[('COMPLETENESS'::character varying)::text, ('FORMAT'::character varying)::text, ('CONSISTENCY'::character varying)::text, ('FRESHNESS'::character varying)::text, ('IDENTITY_MATCH'::character varying)::text])));
CONSTRAINT data_quality_checks_resolution_status_check CHECK (((resolution_status)::text = ANY (ARRAY[('OPEN'::character varying)::text, ('RESOLVED'::character varying)::text, ('ACCEPTED'::character varying)::text])));
CONSTRAINT data_quality_checks_severity_check CHECK (((severity)::text = ANY (ARRAY[('LOW'::character varying)::text, ('MEDIUM'::character varying)::text, ('HIGH'::character varying)::text, ('CRITICAL'::character varying)::text])));
CONSTRAINT data_quality_checks_pkey PRIMARY KEY (check_id);
CONSTRAINT data_quality_checks_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
CONSTRAINT data_quality_checks_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
CONSTRAINT fk_quality_same_company FOREIGN KEY (application_id, company_id) REFERENCES public.credit_applications(application_id, company_id);
```

### public.financial_statements

Синтетическая финансовая отчётность и признак is_verified. Читает feature_builder; загрузка документа не создаёт эти записи.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `statement_id` | `bigint` | нет | `IDENTITY` | Идентификатор statement_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `period_start` | `date` | нет | `—` | Начало периода; календарная дата |
| `period_end` | `date` | нет | `—` | Конец периода; календарная дата |
| `statement_type` | `character varying(20)` | нет | `—` | Вид отчётности; текст/код либо величина по контракту поля |
| `revenue` | `numeric(18,2)` | да | `—` | Выручка периода; деньги; валюта строки, в DEMO RUB |
| `cost_of_sales` | `numeric(18,2)` | да | `—` | Себестоимость; деньги; валюта строки, в DEMO RUB |
| `gross_profit` | `numeric(18,2)` | да | `—` | Валовая прибыль; деньги; валюта строки, в DEMO RUB |
| `operating_expenses` | `numeric(18,2)` | да | `—` | Операционные расходы; деньги; валюта строки, в DEMO RUB |
| `operating_profit` | `numeric(18,2)` | да | `—` | Операционная прибыль; деньги; валюта строки, в DEMO RUB |
| `net_profit` | `numeric(18,2)` | да | `—` | Чистая прибыль; деньги; валюта строки, в DEMO RUB |
| `total_assets` | `numeric(18,2)` | да | `—` | Активы всего; деньги; валюта строки, в DEMO RUB |
| `current_assets` | `numeric(18,2)` | да | `—` | Оборотные активы; деньги; валюта строки, в DEMO RUB |
| `cash_and_equivalents` | `numeric(18,2)` | да | `—` | Денежные средства и эквиваленты; деньги; валюта строки, в DEMO RUB |
| `short_term_liabilities` | `numeric(18,2)` | да | `—` | Краткосрочные обязательства; деньги; валюта строки, в DEMO RUB |
| `total_liabilities` | `numeric(18,2)` | да | `—` | Обязательства всего; деньги; валюта строки, в DEMO RUB |
| `equity` | `numeric(18,2)` | да | `—` | Собственный капитал; деньги; валюта строки, в DEMO RUB |
| `source_document_id` | `text` | да | `—` | Идентификатор source_document_id; идентификатор / номер |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |
| `is_verified` | `boolean` | да | `—` | Верифицированность отчётности; логический признак |

Ограничения (включая PK/FK):

```sql
CONSTRAINT financial_statements_check CHECK ((period_end >= period_start));
CONSTRAINT financial_statements_statement_type_check CHECK (((statement_type)::text = ANY (ARRAY[('ANNUAL'::character varying)::text, ('INTERIM'::character varying)::text, ('MANAGEMENT'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT financial_statements_company_id_period_start_period_end_sta_key UNIQUE (company_id, period_start, period_end, statement_type);
CONSTRAINT financial_statements_pkey PRIMARY KEY (statement_id);
CONSTRAINT financial_statements_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_financial_statements_company_period ON public.financial_statements USING btree (company_id, period_end);
```

### public.guarantors

Структура поручителей заявки. Отдельный полноценный процесс проверки поручителя не подключён.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `guarantor_id` | `bigint` | нет | `IDENTITY` | Идентификатор guarantor_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `guarantor_type` | `character varying(20)` | нет | `—` | Тип поручителя; текст/код либо величина по контракту поля |
| `name` | `text` | нет | `—` | Наименование; текст/код либо величина по контракту поля |
| `inn` | `character varying(12)` | да | `—` | ИНН; текст/код либо величина по контракту поля |
| `ogrn` | `character varying(13)` | да | `—` | ОГРН; текст/код либо величина по контракту поля |
| `ogrnip` | `character varying(15)` | да | `—` | ОГРНИП; текст/код либо величина по контракту поля |
| `relationship_type` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Связь с заёмщиком; текст/код либо величина по контракту поля |
| `existing_obligations_amount` | `numeric(18,2)` | да | `—` | Обязательства поручителя; деньги; валюта строки, в DEMO RUB |
| `financial_capacity_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Состояние платёжеспособности поручителя; текст/код либо величина по контракту поля |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT guarantors_existing_obligations_amount_check CHECK (((existing_obligations_amount IS NULL) OR (existing_obligations_amount >= (0)::numeric)));
CONSTRAINT guarantors_financial_capacity_status_check CHECK (((financial_capacity_status)::text = ANY (ARRAY[('SUFFICIENT'::character varying)::text, ('INSUFFICIENT'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT guarantors_guarantor_type_check CHECK (((guarantor_type)::text = ANY (ARRAY[('INDIVIDUAL'::character varying)::text, ('INDIVIDUAL_ENTREPRENEUR'::character varying)::text, ('LEGAL_ENTITY'::character varying)::text])));
CONSTRAINT guarantors_relationship_type_check CHECK (((relationship_type)::text = ANY (ARRAY[('OWNER'::character varying)::text, ('DIRECTOR'::character varying)::text, ('RELATED_PARTY'::character varying)::text, ('OTHER'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT guarantors_pkey PRIMARY KEY (guarantor_id);
CONSTRAINT guarantors_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
```

### public.legal_events

Сведения юридических источников. Скоринг читает из БД; живой реестр не вызывается.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `legal_event_id` | `bigint` | нет | `IDENTITY` | Идентификатор legal_event_id; идентификатор / номер |
| `company_id` | `bigint` | нет | `—` | Идентификатор company_id; идентификатор / номер |
| `source_name` | `character varying(20)` | нет | `—` | Источник; текст/код либо величина по контракту поля |
| `source_record_id` | `text` | да | `—` | Идентификатор source_record_id; идентификатор / номер |
| `event_type` | `character varying(30)` | нет | `—` | Вид события; текст/код либо величина по контракту поля |
| `event_date` | `date` | да | `—` | Дата события; календарная дата |
| `case_number` | `character varying(100)` | да | `—` | Номер дела; текст/код либо величина по контракту поля |
| `counterparty_name` | `text` | да | `—` | Наименование контрагента; текст/код либо величина по контракту поля |
| `amount` | `numeric(18,2)` | да | `—` | Сумма; деньги; валюта строки, в DEMO RUB |
| `event_status` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Состояние события; текст/код либо величина по контракту поля |
| `company_role` | `character varying(20)` | нет | `'UNKNOWN'::character varying` | Роль компании в деле; текст/код либо величина по контракту поля |
| `description` | `text` | да | `—` | Описание; текст/код либо величина по контракту поля |
| `source_checked_at` | `timestamp with time zone` | да | `—` | Момент source_checked_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT legal_events_amount_check CHECK (((amount IS NULL) OR (amount >= (0)::numeric)));
CONSTRAINT legal_events_company_role_check CHECK (((company_role)::text = ANY (ARRAY[('PLAINTIFF'::character varying)::text, ('DEFENDANT'::character varying)::text, ('DEBTOR'::character varying)::text, ('CREDITOR'::character varying)::text, ('OTHER'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT legal_events_event_status_check CHECK (((event_status)::text = ANY (ARRAY[('OPEN'::character varying)::text, ('IN_PROGRESS'::character varying)::text, ('CLOSED'::character varying)::text, ('TERMINATED'::character varying)::text, ('UNKNOWN'::character varying)::text])));
CONSTRAINT legal_events_event_type_check CHECK (((event_type)::text = ANY (ARRAY[('COURT_CASE'::character varying)::text, ('ENFORCEMENT_PROCEEDING'::character varying)::text, ('TAX_DEBT'::character varying)::text, ('BANKRUPTCY'::character varying)::text, ('OTHER'::character varying)::text])));
CONSTRAINT legal_events_source_name_check CHECK (((source_name)::text = ANY (ARRAY[('KAD'::character varying)::text, ('FNS'::character varying)::text, ('FEDRESURS'::character varying)::text, ('FSSP'::character varying)::text])));
CONSTRAINT legal_events_pkey PRIMARY KEY (legal_event_id);
CONSTRAINT legal_events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_legal_events_company_date ON public.legal_events USING btree (company_id, event_date);
```

### public.macro_indicators

Макроиндикаторы. Читает экономический расчёт; KEY_RATE в seed — демо-значение, не онлайн-ставка ЦБ.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `indicator_id` | `bigint` | нет | `IDENTITY` | Идентификатор indicator_id; идентификатор / номер |
| `indicator_code` | `character varying(50)` | нет | `—` | Код индикатора; текст/код либо величина по контракту поля |
| `indicator_value` | `numeric(12,4)` | нет | `—` | Значение индикатора; семантика определяется кодом показателя/потребителем; DDL единицу не закрепляет |
| `effective_date` | `date` | нет | `—` | Дата действия; календарная дата |
| `source` | `character varying(100)` | нет | `—` | Источник; текст/код либо величина по контракту поля |
| `loaded_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент loaded_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT macro_indicators_code_not_blank CHECK ((btrim((indicator_code)::text) <> ''::text));
CONSTRAINT macro_indicators_key_rate_range CHECK ((((indicator_code)::text <> 'KEY_RATE'::text) OR (indicator_value <= (100)::numeric)));
CONSTRAINT macro_indicators_source_not_blank CHECK ((btrim((source)::text) <> ''::text));
CONSTRAINT macro_indicators_value_nonnegative CHECK ((indicator_value >= (0)::numeric));
CONSTRAINT macro_indicators_pkey PRIMARY KEY (indicator_id);
CONSTRAINT macro_indicators_unique_observation UNIQUE (indicator_code, effective_date, source);
```

Индексы и триггеры:

```sql
CREATE INDEX macro_indicators_latest_idx ON public.macro_indicators USING btree (indicator_code, effective_date DESC);
```

### public.risk_policy_parameters

Версии экономической политики. Читает скоринг; runtime не изменяет финансовые допущения.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `policy_id` | `bigint` | нет | `IDENTITY` | Идентификатор policy_id; идентификатор / номер |
| `product_code` | `character varying(3)` | нет | `—` | Код кредитного продукта; текст/код либо величина по контракту поля |
| `policy_version` | `character varying(50)` | нет | `—` | Версия политики; текст/код либо величина по контракту поля |
| `funding_spread_pct` | `numeric(8,4)` | нет | `—` | Спред фондирования; проценты (шкала 0–100); ставка — % годовых |
| `operating_cost_pct` | `numeric(8,4)` | нет | `—` | Операционные издержки; проценты (шкала 0–100); ставка — % годовых |
| `required_margin_pct` | `numeric(8,4)` | нет | `—` | Целевая маржа; проценты (шкала 0–100); ставка — % годовых |
| `lgd_pct` | `numeric(8,4)` | нет | `—` | LGD; проценты (шкала 0–100); ставка — % годовых |
| `effective_from` | `date` | нет | `—` | Начало действия; календарная дата |
| `effective_to` | `date` | да | `—` | Конец действия; календарная дата |
| `created_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент created_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT risk_policy_parameters_dates CHECK (((effective_to IS NULL) OR (effective_to >= effective_from)));
CONSTRAINT risk_policy_parameters_lgd_range CHECK (((lgd_pct >= (0)::numeric) AND (lgd_pct <= (100)::numeric)));
CONSTRAINT risk_policy_parameters_margin_range CHECK (((required_margin_pct >= (0)::numeric) AND (required_margin_pct <= (100)::numeric)));
CONSTRAINT risk_policy_parameters_operating_range CHECK (((operating_cost_pct >= (0)::numeric) AND (operating_cost_pct <= (100)::numeric)));
CONSTRAINT risk_policy_parameters_spread_range CHECK (((funding_spread_pct >= ('-100'::integer)::numeric) AND (funding_spread_pct <= (100)::numeric)));
CONSTRAINT risk_policy_parameters_version_not_blank CHECK ((btrim((policy_version)::text) <> ''::text));
CONSTRAINT risk_policy_parameters_pkey PRIMARY KEY (policy_id);
CONSTRAINT risk_policy_parameters_product_version_uk UNIQUE (product_code, policy_version);
CONSTRAINT risk_policy_parameters_product_fk FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);
```

Индексы и триггеры:

```sql
CREATE INDEX risk_policy_parameters_lookup_idx ON public.risk_policy_parameters USING btree (product_code, effective_from DESC);
```

### public.scoring_results

Результат модели и feature_snapshot. Пишет scoring persistence; кабинет показывает assessment через связанный снимок.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `scoring_result_id` | `bigint` | нет | `IDENTITY` | Идентификатор scoring_result_id; идентификатор / номер |
| `application_id` | `bigint` | нет | `—` | Идентификатор application_id; идентификатор / номер |
| `model_version` | `character varying(50)` | нет | `—` | Версия модели; текст/код либо величина по контракту поля |
| `scored_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент scored_at; дата/время PostgreSQL; with time zone — момент времени |
| `score` | `numeric(12,4)` | да | `—` | Скоринговый балл; семантика определяется кодом показателя/потребителем; DDL единицу не закрепляет |
| `pd` | `numeric(8,6)` | да | `—` | Вероятность дефолта; вероятность, доля 0–1 |
| `risk_grade` | `character varying(20)` | нет | `'UNRATED'::character varying` | Категория риска (runtime UNRATED); текст/код либо величина по контракту поля |
| `feature_snapshot` | `jsonb` | да | `—` | Снимок признаков; структура JSON; контракт задаёт потребитель |
| `source_snapshot_date` | `timestamp with time zone` | да | `—` | Дата исходного снимка; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT scoring_results_pd_check CHECK (((pd IS NULL) OR ((pd >= (0)::numeric) AND (pd <= (1)::numeric))));
CONSTRAINT scoring_results_risk_grade_check CHECK (((risk_grade)::text = ANY (ARRAY[('LOW'::character varying)::text, ('MEDIUM'::character varying)::text, ('HIGH'::character varying)::text, ('VERY_HIGH'::character varying)::text, ('UNRATED'::character varying)::text])));
CONSTRAINT scoring_results_pkey PRIMARY KEY (scoring_result_id);
CONSTRAINT uq_scoring_application UNIQUE (scoring_result_id, application_id);
CONSTRAINT scoring_results_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);
```

Индексы и триггеры:

```sql
CREATE INDEX idx_scoring_results_application_date ON public.scoring_results USING btree (application_id, scored_at);
```

### public.user_accounts

Синтетические пользователи. Cabinet.login/session читает; пароли не экспортируются в state. Seed содержит демонстрационные пароли, не промышленное хранилище идентификации.

| Поле | Тип | Nullable | Default / identity | Единица и смысл |
|---|---|---|---|---|
| `user_id` | `bigint` | нет | `—` | Идентификатор user_id; идентификатор / номер |
| `last_name` | `character varying(100)` | нет | `—` | Фамилия; текст/код либо величина по контракту поля |
| `first_name` | `character varying(100)` | нет | `—` | Имя; текст/код либо величина по контракту поля |
| `middle_name` | `character varying(100)` | да | `—` | Отчество; текст/код либо величина по контракту поля |
| `login` | `character varying(100)` | нет | `—` | Логин; текст/код либо величина по контракту поля |
| `password` | `text` | нет | `—` | Демонстрационный пароль (не возвращается API); текст/код либо величина по контракту поля |
| `role` | `character varying(20)` | нет | `—` | Роль учётной записи; текст/код либо величина по контракту поля |
| `company_id` | `bigint` | да | `—` | Идентификатор company_id; идентификатор / номер |
| `is_active` | `boolean` | нет | `true` | Активность учётной записи; логический признак |
| `created_at` | `timestamp with time zone` | нет | `CURRENT_TIMESTAMP` | Момент created_at; дата/время PostgreSQL; with time zone — момент времени |

Ограничения (включая PK/FK):

```sql
CONSTRAINT chk_user_company_role CHECK (((((role)::text = 'CLIENT'::text) AND (company_id IS NOT NULL)) OR (((role)::text = 'BANK_EMPLOYEE'::text) AND (company_id IS NULL))));
CONSTRAINT user_accounts_role_check CHECK (((role)::text = ANY (ARRAY[('CLIENT'::character varying)::text, ('BANK_EMPLOYEE'::character varying)::text])));
CONSTRAINT user_accounts_login_key UNIQUE (login);
CONSTRAINT user_accounts_pkey PRIMARY KEY (user_id);
```

Индексы и триггеры:

```sql
CREATE UNIQUE INDEX ux_user_accounts_company ON public.user_accounts USING btree (company_id) WHERE (company_id IS NOT NULL);
```

## Служебные схемы

Точные определения ниже включают поля, nullable, DEFAULT, PK/FK и CHECK. Для сессий token_hash — хэш, content — байты, sha256/input_hash/offer_hash — контрольные суммы, version — целая версия, form_state/payload/result/details — JSON-контракты кабинета; *_at — timestamptz. Эти определения не изменяют public.

### aurelius_cabinet.sessions

Хэши сессионных токенов и срок. Cabinet.login/session/logout читает и пишет.

Источник: [005_cabinet.sql](../../personalCab/prom_v2/migrations/005_cabinet.sql).

```sql
CREATE TABLE aurelius_cabinet.sessions (

    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    expires_at TIMESTAMPTZ NOT NULL

);
```

### aurelius_cabinet.application_state

Версия, form_state и время обновления; Cabinet.mutate/save читает и пишет.

Источник: [005_cabinet.sql](../../personalCab/prom_v2/migrations/005_cabinet.sql).

```sql
CREATE TABLE aurelius_cabinet.application_state (

    application_id BIGINT PRIMARY KEY REFERENCES public.credit_applications(application_id),
    version INTEGER NOT NULL DEFAULT 1,
    form_state JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()

);
```

### aurelius_cabinet.receipts

Идемпотентные результаты и pending_score; Cabinet.action читает и пишет.

Источник: [005_cabinet.sql](../../personalCab/prom_v2/migrations/005_cabinet.sql).

```sql
CREATE TABLE aurelius_cabinet.receipts (

    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    request_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    result JSONB NOT NULL,
    PRIMARY KEY(user_id, request_id)

);
```

### aurelius_cabinet.events

События действий, назначения и аттестации; Cabinet.event пишет, state читает.

Источник: [005_cabinet.sql](../../personalCab/prom_v2/migrations/005_cabinet.sql).

```sql
CREATE TABLE aurelius_cabinet.events (

    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()

);
```

### aurelius_cabinet.documents

Байты непроверенных PDF/CSV, автор, SHA256; upload пишет, авторизованное скачивание читает.

Источник: [006_cabinet_documents.sql](../../personalCab/prom_v2/migrations/006_cabinet_documents.sql).

```sql
CREATE TABLE aurelius_cabinet.documents (

    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    uploaded_by BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    data_request_id BIGINT REFERENCES public.application_data_requests(request_id),
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('application/pdf', 'text/csv')),
    content BYTEA NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 10485760),
    sha256 TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('CLIENT_UPLOAD', 'EMPLOYEE_UPLOAD')),
    processing_status TEXT NOT NULL DEFAULT 'STORED_UNVERIFIED'
        CHECK (processing_status = 'STORED_UNVERIFIED'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()

);
```

### aurelius_cabinet.assignments

Ответственный; claim/release пишет, проверка полномочий читает.

Источник: [007_cabinet_assignments.sql](../../personalCab/prom_v2/migrations/007_cabinet_assignments.sql).

```sql
CREATE TABLE aurelius_cabinet.assignments (

    application_id BIGINT PRIMARY KEY REFERENCES public.credit_applications(application_id),
    employee_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()

);
```

### aurelius_cabinet.calculation_inputs

Отпечаток входов и оффера расчёта; guarded_score пишет, freshness читает.

Источник: [008_cabinet_freshness.sql](../../personalCab/prom_v2/migrations/008_cabinet_freshness.sql).

```sql
CREATE TABLE aurelius_cabinet.calculation_inputs (

    input_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    snapshot_id BIGINT NOT NULL REFERENCES public.application_snapshots(snapshot_id),
    input_hash TEXT NOT NULL,
    offer_hash TEXT,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()

);
```

### aurelius_cabinet.offer_publications

Связь опубликованного оффера с расчётом и решением; review пишет, accept читает.

Источник: [008_cabinet_freshness.sql](../../personalCab/prom_v2/migrations/008_cabinet_freshness.sql).

```sql
CREATE TABLE aurelius_cabinet.offer_publications (

    offer_id BIGINT PRIMARY KEY REFERENCES public.application_product_terms(offer_id),
    input_id BIGINT NOT NULL REFERENCES aurelius_cabinet.calculation_inputs(input_id),
    decision_id BIGINT NOT NULL REFERENCES public.credit_decisions(decision_id),
    offer_hash TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now()

);
```

### aurelius_cabinet.stale_offers

Причина снятия устаревшего оффера; freshness/accept пишет, state читает.

Источник: [008_cabinet_freshness.sql](../../personalCab/prom_v2/migrations/008_cabinet_freshness.sql).

```sql
CREATE TABLE aurelius_cabinet.stale_offers (

    offer_id BIGINT PRIMARY KEY REFERENCES public.application_product_terms(offer_id),
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason TEXT NOT NULL

);
```

### aurelius_cabinet.dialogues

Приватный Case payload по пользователю и заявке; run_dialogue читает и пишет.

Источник: [009_cabinet_dialogues.sql](../../personalCab/prom_v2/migrations/009_cabinet_dialogues.sql).

```sql
CREATE TABLE aurelius_cabinet.dialogues (

    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    company_id BIGINT NOT NULL REFERENCES public.companies(company_id),
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(application_id,user_id)

);
```

### aurelius_deploy.seed_validation

Маркер сверки начального дампа; создаёт restore, init читает/обновляет. Не резервная копия.

Источник: [00_restore.sh](../../deploy/00_restore.sh).

```sql
CREATE TABLE aurelius_deploy.seed_validation (
singleton boolean PRIMARY KEY CHECK (singleton), validated_at timestamptz NOT NULL DEFAULT now()
);
```
