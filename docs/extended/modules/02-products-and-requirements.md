# Продукт и анкета

## Назначение

Собрать достаточное обращение для конкретного продукта и формы бизнеса.

## Входы и выходы

R01/R02/R03, реквизиты, сумма/срок/цель, согласия → сохранённая анкета и отправленная заявка либо список ошибок.

## Реализация

- [personalCab/prom_v2/cabinet.py](../../../personalCab/prom_v2/cabinet.py)
- [personalCab/prom_v2/declared_facts.py](../../../personalCab/prom_v2/declared_facts.py)
- [personalCab/web/src/business/BusinessFormSteps.tsx](../../../personalCab/web/src/business/BusinessFormSteps.tsx)
- [personalCab/prom_v2/adapters.py](../../../personalCab/prom_v2/adapters.py)

## Состояние БД

credit_applications, application_details, application_product_details, application_field_requirements/values/history; form_state в application_state. В seed 99 требований к R01–R03, применимость зависит от ИП/юрлица.

## Ошибки

Неподдерживаемый продукт, неполные/невалидные поля, отсутствующие согласия и устаревшая версия отклоняются до подачи. Отправка и последующий расчёт — разные фазы.

## Проверки и связи

test_incomplete_submission_rolls_back; test_dialogue_nine_company_facts_confirm_into_questionnaire_only; http_form_steps.test.tsx. Это ссылки на предусмотренные проверки, а не протокол нового запуска. Основные интеграционные тесты — [test_cabinet](../../../personalCab/prom_v2/tests/test_cabinet.py).

16 направлений справочника помогают выбрать задачу; только три имеют транзакционный контур. После submit запускается этап 04 с банковскими данными этапа 03.

[Карта этапов](README.md) · [БД](../database-reference.md) · [HTTP-интеграция](../backend-integration.md)
