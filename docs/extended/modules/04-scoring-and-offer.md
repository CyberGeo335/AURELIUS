# Скоринг и черновые условия

## Назначение

Оценить риск и доступные условия по воспроизводимому входу.

## Входы и выходы

application_id → Assessment: eligibility, PD, risk limit, recommendation, причины, возможный черновик оффера и audit.

## Реализация

- [scoring/main/database.py](../../../scoring/main/database.py)
- [scoring/main/pipeline.py](../../../scoring/main/pipeline.py)
- [scoring/main/decision_engine/engine.py](../../../scoring/main/decision_engine/engine.py)
- [scoring/main/credit_offer/calculator.py](../../../scoring/main/credit_offer/calculator.py)
- [scoring/main/ml_scoring/predictor.py](../../../scoring/main/ml_scoring/predictor.py)

## Состояние БД

Чтение финансов, продукта и политики; запись scoring_results, credit_decisions, application_snapshots и возможного application_product_terms. calculation_inputs связывает результат с отпечатком.

## Ошибки

DB_INPUTS_UNAVAILABLE означает ручную проверку без PD; InputError/ConfigurationError — сбой входа/сервиса. Скоринг не переводит заявку в APPROVED.

## Проверки и связи

scoring/main/tests/test_pipeline.py; scoring/main/tests/test_predictor_semantics.py; test_scoring_outage_retries_submission_without_duplicate_mutation. Это ссылки на предусмотренные проверки, а не протокол нового запуска. Основные интеграционные тесты — [test_cabinet](../../../personalCab/prom_v2/tests/test_cabinet.py).

Кандидат оффера DRAFT доступен сотруднику этапа 05. Наличие расчёта не означает публикацию клиенту.

[Карта этапов](README.md) · [БД](../database-reference.md) · [HTTP-интеграция](../backend-integration.md)
