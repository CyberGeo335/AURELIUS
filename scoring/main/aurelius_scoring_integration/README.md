# AURELIUS — интеграция ML Scoring

> **Исторический прототип.** Эта папка сохранена для воспроизведения исходной
> интеграции с моделью trial_0027. Текущий backend-вход, модель с монотонностью,
> decision engine и подбор условий описаны в [../README.md](../README.md) и
> [../INTEGRATION.md](../INTEGRATION.md). Новый код не следует подключать через
> этот старый scoring_service.py.

Этот прототип рассчитывает накопленную PD на горизонтах, использованных при оценке модели, и может записать результат в `scoring_results` PostgreSQL.

**Ограничение:** признаки из базы пока не извлекаются автоматически. Требуется сопоставление `features.json` и исходных полей таблиц, включая правила расчёта агрегатов. Не подставляйте фиктивные значения в недостающие признаки.

## Требования

`pip install catboost pandas numpy sqlalchemy "psycopg[binary]"`

Файлы из обучающего проекта:
- `models/experiments/survival_v3_optuna_stage2/models/trial_0027.cbm` (либо проверенная копия `best_model.cbm`)
- `models/experiments/survival_v3_discrete_time/features.json`
- `episode.json` — JSON-словарь признаков **одной заявки** в формате обучения; `month_on_book` рассчитывается программой.

## Запуск без БД

```bash
python scoring_service.py --model trial_0027.cbm --features-config features.json --episode-json episode.json --term-months 36
```

## Сохранение результата в БД

```bash
python scoring_service.py --model trial_0027.cbm --features-config features.json --episode-json episode.json --term-months 36 --database-url "postgresql+psycopg://postgres:PASSWORD@localhost:5433/business_scoring" --application-id 1 --save
```

`scoring_results.pd` содержит PD на **наибольшем оценённом горизонте**, а не обязательно на полный срок кредита. `feature_snapshot` сохраняет горизонт, набор признаков и PD на всех поддерживаемых горизонтах. `risk_grade` остаётся `UNRATED` до утверждения кредитной политики.

**Важно:** в `credit_decisions` текущая схема БД допускает `APPROVE`/`REJECT`, а не `APPROVED`/`REJECTED`; интеграция Decision Engine должна учитывать это.
