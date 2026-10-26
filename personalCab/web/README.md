# Веб-кабинет AURELIUS

Проверено по коду коммита `6a9a4c1` (ветка `chore/cleanup-legacy`).

React/TypeScript SPA для клиента и сотрудника банка. Текущий запуск — HTTP-режим `VITE_API_MODE=http`, сервер `personalCab.prom_v2.cabinet_server`, API `/api/v2`.

Полное решение собирается корневым Dockerfile; контекст сборки — корень репозитория. Запуск сервисов — по [README](../../README.md#запуск), настройки — в [09](../../docs/09-deployment.md#4-переменные-окружения).

## Разработка

Из `personalCab/web` выполните `npm ci`, затем `npm test` или `npm run lint`. HTTP-сборка: `VITE_API_MODE=http npm run build` в POSIX shell. В PowerShell сначала задайте `$env:VITE_API_MODE = 'http'`, затем выполните `npm run build`.

Для разработки с уже запущенным backend: `VITE_API_MODE=http npm run dev`. Vite слушает `127.0.0.1:5174` и направляет `/api` на backend `127.0.0.1:5173` согласно `vite.config.ts`.

## Навигация

- [Сценарии](../../docs/03-demo-scenarios.md)
- [API и роли](../../docs/06-api.md)
- [Тестовый инвентарь](../../docs/08-testing.md#12-фронт)
- [Вход и сессия](src/api/AUTH.md)

Исторические материалы интерфейса сохранены в `docs/history/reports/` и не являются инструкцией текущего запуска.
