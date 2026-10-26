# Вход и диалог

## Назначение

Авторизовать представителя компании и преобразовать текст в подтверждаемое предложение.

## Входы и выходы

Cookie/логин, текст, версия и форма черновика → сессия, история, pending или ошибка.

## Реализация

- [personalCab/prom_v2/cabinet_server.py](../../../personalCab/prom_v2/cabinet_server.py)
- [personalCab/prom_v2/cabinet_assistant.py](../../../personalCab/prom_v2/cabinet_assistant.py)
- [personalCab/prom_v2/agent.py](../../../personalCab/prom_v2/agent.py)
- [personalCab/prom_v2/adapters.py](../../../personalCab/prom_v2/adapters.py)

## Состояние БД

public.user_accounts читается при входе; aurelius_cabinet.sessions хранит хэш токена; dialogues хранит приватный payload; подтверждение пишет поля анкеты.

## Ошибки

LOGIN_REQUIRED, STALE_PROPOSAL, STALE_CASE_VERSION, EXTRACTION_UNAVAILABLE. Вне DRAFT диалог заполнения отклоняется.

## Проверки и связи

test_http_origin_cookie_login_and_logout, test_v2_dialogue_confirmation_form_sync_and_isolation, test_dialogue_model_outage_is_retryable_without_fake_history. Это ссылки на предусмотренные проверки, а не протокол нового запуска. Основные интеграционные тесты — [test_cabinet](../../../personalCab/prom_v2/tests/test_cabinet.py).

Подтверждённые поля поступают этапу 02; они не являются банковской финансовой историей этапа 03.

[Карта этапов](README.md) · [БД](../database-reference.md) · [HTTP-интеграция](../backend-integration.md)
