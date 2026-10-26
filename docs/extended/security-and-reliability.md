# Безопасность и надёжность: реализованные границы

## Модель доверия

Браузер и текст модели — недоверенные входы. Сервер определяет идентичность по сессии, проверяет владение и роль. БД хранит бизнес-данные, метаданные процесса и исходные синтетические наблюдения. Ollama формирует предложение; финансовая политика и переходы остаются в коде. Доступ оператора к очереди шире доступа клиента; право решения дополнительно ограничено назначением.

| Механизм | Реализация | Проверка в репозитории | Практическая граница |
|---|---|---|---|
| Сессия | cabinet.login/session; token_hash, срок 8 ч | test_auth_uses_v3_and_clears_cookie_session | хэшируется токен; демонстрационные пароли в user_accounts сравниваются напрямую, это не password hashing |
| Cookie и Origin | Handler.respond/do_POST | test_http_origin_cookie_login_and_logout | HttpOnly/SameSite=Strict; Secure отсутствует, TLS/SSO не реализованы |
| Компания и заявка | Cabinet.owned, company_id из session | test_ownership_version_and_idempotent_create | клиент не выбирает доверенную идентичность телом запроса |
| Приватный диалог | project и dialogues по application_id/user_id | test_v2_dialogue_confirmation_form_sync_and_isolation | сотрудник не получает текст диалога |
| Причины решения | Cabinet.project, точный allowlist кодов сотрудника | test_actual_scorer_result_review_accept_and_client_redaction | клиент получает только BANK_APPROVE, BANK_REJECT, BANK_REQUEST_DATA; внутренние причины остаются у сотрудника |
| Проверка извлечения | checked_extraction, validate_extraction, declared_facts | test_agent.py, test_declared_facts.py | типизация дополняется проверкой значения и цитаты |
| Версия | application_state.version и expected_version | test_ownership_version_and_idempotent_create | конфликт возвращает STALE_CASE_VERSION; не терять чужое сохранение |
| Повторы | receipts(user_id,request_id), input_hash | test_scoring_outage_retries_submission_without_duplicate_mutation | одинаковое тело повторяется; изменённое отвергается |
| Конкурентное назначение | row lock, assignments | test_concurrent_assignment_and_release_permissions | только ответственный делает score/verify/review |
| Устаревание | cabinet_freshness, calculation_inputs, offer_publications | test_actual_scorer_result_review_accept_and_client_redaction | SCORING_STALE до одобрения, OFFER_STALE при принятии |
| Блокировки источников | SHARE ROW EXCLUSIVE, advisory locks | test_input_locks_block_external_updates_and_inserts | блокируются также вставки внешних писателей; это локальная сериализация |
| Документы | кабинет документов, BYTEA, SHA256, лимиты | test_document_bytes_scope_retry_and_open_request и test_cabinet_documents.py | только структурная проверка формата, не OCR/антивирус/юридическая экспертиза |
| Аудит | events, application_field_history, snapshots; историю полей пишет только триггер v4 | test_employee_attestation_preserves_source_facts; схема v4 | журнал verify не делает исходные данные VERIFIED; неизменившееся значение не создаёт запись истории |
| Отказ модели | EXTRACTION_UNAVAILABLE, откат хода | test_dialogue_model_outage_is_retryable_without_fake_history | форма остаётся доступным способом ввода |
| Отказ расчёта | pending_score и повтор | test_scoring_outage_retries_submission_without_duplicate_mutation | отправленная заявка может сохраниться до ошибки расчёта |

Имена test_* приведены из [test_cabinet.py](../../personalCab/prom_v2/tests/test_cabinet.py), остальные файлы — [tests](../../personalCab/prom_v2/tests/). Наличие проверки не означает её новый успешный прогон. Протоколы и инвентарь разделены в [08](../08-testing.md).

## Согласованность и след решения

Доменная мутация и её начальная квитанция находятся в одной транзакции psycopg. Скоринг сохраняет результат отдельно через SQLAlchemy. Advisory locks связывают фазы, pending_score позволяет продолжить незавершённый запрос. Блокировки входных таблиц и сравнение before/after со snapshot защищают публикацию от изменения данных в процессе расчёта. В отпечаток входят экономические входы, дата расчёта, код и конфигурация библиотеки, модель. Поэтому обновление модели также требует нового расчёта.

История полей и решения сохраняются отдельно от актуального состояния; в v4 есть триггеры запрета мутации аудита. Это не доказательство защиты от привилегированного администратора БД. offer_publications связывает опубликованный оффер с конкретным решением и calculation_inputs; stale_offers объясняет техническое снятие предложения. Такой исход не равен отказу сотрудника.

## Входы, файлы и диагностика

HTTP ограничивает длину тела и требует JSON-объект. SQL передаёт значения параметрами; динамические имена в freshness оформлены psycopg.sql.Identifier. Полномочия проверяются повторно на сервере независимо от состояния кнопки. Документы доступны через авторизованный endpoint, отдаются attachment с nosniff; имя безопасно кодируется в Content-Disposition. SHA256 обеспечивает обнаружение различий, но не доверие к содержимому.

Handler не пишет тела, пароли, cookie и query в стандартный request log. Клиент получает общую ошибку БД, а не текст драйвера. При недоступной БД ответ 503; наличие отказа не должно порождать REJECT. Промышленная наблюдаемость с обезличенными событиями и метриками требует отдельной реализации.

## План внедрения с критериями

| Направление | Предлагаемый критерий перехода |
|---|---|
| Идентификация | интеграционный тест IdP, отзыв сессий, матрица полномочий и безопасное хранение секретов |
| TLS и защита POST | проверка HTTPS, Secure cookie, корректного доверенного Origin за proxy и отрицательных cross-origin запросов |
| Нагрузка | измерены задержки и ожидания table/advisory locks; целевой профиль нагрузки согласован до пилота |
| Резервное восстановление | автоматический backup и успешное восстановление в чистую БД, проверены целостность и согласованные RPO/RTO |
| Наблюдаемость | корреляция request_id без чувствительных данных, алерты на 5xx/зависшие pending_score/ошибки модели |
| Документы | угрозы и политика хранения, антивирус и проверка содержимого, если это требуется целевым контуром |

Том PostgreSQL сохраняет состояние между перезапусками, но не заменяет резервное копирование. HA, SSO и устойчивость к произвольным атакам не заявляются как свойства текущего стенда. Последовательность работ — [roadmap](roadmap-and-validation.md).
