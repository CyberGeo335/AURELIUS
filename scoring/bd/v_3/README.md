# Версия БД v3 — актуальная

Полный снимок локальной `business_scoring` после добавления экономической политики
`AURELIUS_MVP_20261024_V1` и официального наблюдения KEY_RATE=14%.

- `business_scoring_wauth.backup`: custom-format pg_dump, структура и все данные,
  включая `user_accounts`, последовательности, ограничения и триггеры.
- `schema_actual.sql`: отдельно структура той же версии.
- `manifest.json`: SHA256 файлов и число строк во всех 35 таблицах.

Оба дампа сняты из одного экспортированного MVCC-снимка. Полный backup восстановлен
в отдельную временную PostgreSQL-базу; числа строк во всех 35 таблицах совпали.
В этой версии `risk_policy_parameters` содержит 3 строки, `macro_indicators` — 1.
Пароли ролей PostgreSQL/настройки кластера не входят в pg_dump базы.

Восстанавливать в новую пустую БД:

```powershell
pg_restore --no-owner --no-privileges --exit-on-error -d NEW_DATABASE "bd/v_3 (actual)/business_scoring_wauth.backup"
```

Предыдущая версия сохранена в `bd/v_2`, без отметки `(actual)`.
