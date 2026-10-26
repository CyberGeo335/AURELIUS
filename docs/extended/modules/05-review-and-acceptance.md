# Рассмотрение и принятие

## Назначение

Зафиксировать мотивированный банковский результат и согласие клиента с опубликованными условиями.

## Входы и выходы

Назначенная заявка, актуальный расчёт, проверки/ответы → APPROVE/REJECT/REQUEST_DATA; опубликованный оффер → ACCEPTED.

## Реализация

- [personalCab/prom_v2/cabinet.py](../../../personalCab/prom_v2/cabinet.py)
- [personalCab/prom_v2/cabinet_freshness.py](../../../personalCab/prom_v2/cabinet_freshness.py)
- [personalCab/web/src/pages/bank/Review.tsx](../../../personalCab/web/src/pages/bank/Review.tsx)
- [personalCab/web/src/pages/client/ApplicationDetail.tsx](../../../personalCab/web/src/pages/client/ApplicationDetail.tsx)

## Состояние БД

assignments и events фиксируют работу; credit_decisions и application_data_requests — решение/дозапрос; offer_publications — публикация; stale_offers — снятие; application_product_terms.offer_status — принятие.

## Ошибки

ASSIGNEE_REQUIRED, ALREADY_ASSIGNED, SCORING_STALE, OFFER_STALE; открытые дозапросы блокируют одобрение. Загрузка файла отдельно от ответа. После ответа расчёт повторяет сотрудник.

## Проверки и связи

test_concurrent_assignment_and_release_permissions; test_actual_scorer_result_review_accept_and_client_redaction; http_credit.test.tsx. Это ссылки на предусмотренные проверки, а не протокол нового запуска. Основные интеграционные тесты — [test_cabinet](../../../personalCab/prom_v2/tests/test_cabinet.py).

REQUEST_DATA возвращает к этапам 02/03; принятый оффер завершает действующий положительный путь. Подпись и выдача не подключены.

[Карта этапов](README.md) · [БД](../database-reference.md) · [HTTP-интеграция](../backend-integration.md)
