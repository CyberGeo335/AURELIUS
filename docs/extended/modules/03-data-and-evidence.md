# Данные и происхождение

## Назначение

Разделить заявление клиента, наблюдения банка, документ и аттестацию сотрудника.

## Входы и выходы

Компании, операции, отчётность, обязательства и история → версионированный snapshot/model_features с provenance; файлы → STORED_UNVERIFIED.

## Реализация

- [scoring/main/application_service.py](../../../scoring/main/application_service.py)
- [scoring/main/ml_scoring/feature_builder.py](../../../scoring/main/ml_scoring/feature_builder.py)
- [scoring/main/application_facts.py](../../../scoring/main/application_facts.py)
- [personalCab/prom_v2/cabinet_documents.py](../../../personalCab/prom_v2/cabinet_documents.py)

## Состояние БД

companies и финансовые таблицы читаются скорингом; application_field_values содержит CLIENT/UNVERIFIED; documents хранит байты; verify пишет events, не обновляет профиль компании.

## Ошибки

Нужно 13 положительных завершённых месяцев REVENUE в RUB, верифицированная отчётность и известные платежи. Неполнота не заполняется нулями. Повреждённый PDF/CSV или чужая заявка отклоняются.

## Проверки и связи

test_employee_attestation_preserves_source_facts; test_document_bytes_scope_retry_and_open_request; scoring/main/tests. Это ссылки на предусмотренные проверки, а не протокол нового запуска. Основные интеграционные тесты — [test_cabinet](../../../personalCab/prom_v2/tests/test_cabinet.py).

Snapshot и происхождение передаются этапу 04. Недостающие ОКВЭД/дата регистрации в DEMO могут читаться из подтверждённой анкеты; статус UNVERIFIED сохраняется.

[Карта этапов](README.md) · [БД](../database-reference.md) · [HTTP-интеграция](../backend-integration.md)
