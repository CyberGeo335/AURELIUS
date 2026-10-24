# Подключение к backend

Актуально для `dt_monotone_v1`, контрактов `db_auto_v3` / `db_proxy_v2`,
экономической политики `AURELIUS_MVP_20261024_V1`.

## Установка и конфигурация

Код `main` и `main/ml_scoring/model/best_model.cbm` берутся из Git-ветки вместе.
Python-зависимости: `python -m pip install -r main/requirements.txt`.
Подключение задаётся один раз в окружении backend-процесса; пароль не хранится в Git.

CMD:

```cmd
set "DATABASE_URL=postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5433/business_scoring"
```

PowerShell:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:YOUR_PASSWORD@127.0.0.1:5433/business_scoring"
```

Полный актуальный дамп — `bd/v_3 (actual)/business_scoring_wauth.backup`.
Восстановление выполняется в новую пустую БД. Он уже содержит KEY_RATE и три
строки экономической политики. После любого изменения рабочей БД требуется
следующий полный дамп по `bd/README_versions.md`.

## Что передать

```python
from main.database import run_application
from main.schemas import InputError, ConfigurationError

try:
    result = run_application(application_id=123, save=True)
except InputError as exc:
    # Неверный ID/недопустимое состояние заявки: вернуть ошибку вызова.
    ...
except ConfigurationError as exc:
    # Проблема внутренних настроек: обработать как ошибку сервера.
    ...
```

`run_application` возвращает Python `dict`, пригодный для JSON; это не HTTP API.
Endpoint, аутентификация, проверка принадлежности заявки, очередь сотрудника
и финальное подтверждение реализуются backend-командой.

Заявка должна принадлежать авторизованной компании и иметь состояние SUBMITTED
или UNDER_REVIEW. Для расчёта нужны COMPLETE и подтверждённая подача, реквизиты,
13 завершённых месяцев положительной выручки REVENUE/RUB, верифицированная
отчётность, известные платежи/обязательства и история просрочек. CANCELLED и DRAFT
не переиспользуются. Недостаток финансовых данных не компенсируется выдуманными
значениями: возвращается ручная проверка с DB_INPUTS_UNAVAILABLE и без PD.

Всё читается из БД плюс серверная конфигурация main. По умолчанию используются
явные допущения MVP: нейтральный synthetic macro_stress=0, приближённый денежный
поток и коэффициент генератора. Индикативная цена перебирается от публичной
базовой +2 п.п. до 30%, шаг 0.5 п.п. 30% — допущение проекта, не тариф банка.
Если backend передал фиксированную индивидуальную цену через context без
pricing_policy либо есть внешний черновик предложения, эта цена не меняется.
Расширенный интерфейс: `run_application(id, context=..., policy=..., save=...)`.

## Что получить

Сокращённый пример **формата** положительного финансового результата:

```json
{
  "application_id": 123,
  "decision": "MANUAL_REVIEW",
  "automatic_recommendation": "REVIEW_REQUIRED",
  "eligibility_status": "ELIGIBLE",
  "offer": {
    "amount": "3000000.00",
    "term_months": 36,
    "annual_rate_pct": "29.00"
  },
  "risk_assessment": {
    "pd_application_1y": 0.18,
    "pd_application_term": 0.40,
    "pd_limit_1y": 0.1888888889,
    "comparison_horizon_months": 12,
    "annual_rate_pct": "29.00",
    "passes_pd_limit": true
  }
}
```

Полный ответ также содержит `reasons`, `policy_version`, `scoring`, график,
показатели экономики и `audit`. При save=True добавляется `persistence` с ID
записей. Деньги/ставки Decimal сериализуются строками, вероятности — числами
в долях единицы: 0.18 означает 18%, не 0.18%.

| Поля | Как backend должен трактовать |
|---|---|
| MANUAL_REVIEW + POSITIVE + offer | Автоматические проверки пройдены, требуется решение сотрудника |
| MANUAL_REVIEW + REVIEW_REQUIRED | Есть нерешённые проверки/допущения; offer может быть предварительным |
| REJECT + NEGATIVE | При проверенных условиях подходящего предложения нет; причины в reasons |
| scoring/PD = null | Скоринг не был выполнен; это нельзя показывать как PD=0 |

Текущий автоматический путь с proxy оставляет REVIEW_REQUIRED, даже если
финансово найден offer. `APPROVE` библиотека не выдаёт.
Окончательные APPROVE/REJECT и утверждённые условия фиксирует авторизованный
сотрудник через backend; библиотека не реализует endpoint этого подтверждения.

## Лимит PD и сохранение

```text
PD_limit_1y = (R − KEY_RATE − spread − operating_cost − required_margin) / LGD
```

В числах процентов текущей политики: `(R − 20.5) / 45`; например, при R=29%
лимит ≈18.89%. Сравнивается с PD12, рассчитанной **для той же суммы и ставки**.
PD за весь срок показывается отдельно. Для договорного срока 12 месяцев PD12
остаётся вне исходного набора оценённых горизонтов; это отмечено в risk_assessment.
Для отображения/сравнения годовой PD берите risk_assessment.pd_application_1y:
единственная колонка scoring_results.pd хранит PD на наибольшем оценённом горизонте,
который может отличаться от 12 месяцев. Его значение записано в feature_snapshot.

`save=False` — только расчёт; `save=True` — атомарно scoring_results,
credit_decisions, DRAFT application_product_terms и DECISION-аудит.
В credit_decisions при автоматической ручной проверке approved_amount и
approved_term_days остаются NULL. Статус заявки не меняется.
Повтор одного снимка/политики/модели возвращает прежние IDs.
Ошибки БД/сериализации обрабатываются backend отдельно; они не кредитный отказ.

## Проверка без изменения БД

```cmd
python -m main.pipeline --application-id 123
python -m main.batch --diagnostic --as-of 2026-10-24 --product R01 --amount 3000000 --term 36
```

Второй вызов — what-if по 30 бизнесам, независимо от CANCELLED-заявок. Он
допускает отмеченную аппроксимацию короткой истории и предполагает завершение
анкеты/проверок только в памяти. Отчёты main/reports/diagnostic.csv и .json.
Это проверка сценариев, не симуляция фактического одобрения банком.

Качество, ограничения синтетического обучения и исправления:
[ml_scoring/MODEL_REPAIR.md](ml_scoring/MODEL_REPAIR.md).
