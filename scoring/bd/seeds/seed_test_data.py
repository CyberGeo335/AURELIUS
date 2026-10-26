"""
Генератор синтетических тестовых данных для business_scoring.
Создаёт связанные записи в PostgreSQL; реальные данные не использует.

Запуск:
  py -m pip install "psycopg[binary]"
  py seed_test_data.py

Перед запуском укажите пароль PostgreSQL в переменной окружения PG_PASSWORD
или измените DB_CONFIG ниже.
"""

import os
import random
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
import psycopg
from psycopg.types.json import Jsonb

random.seed(42)

DB_CONFIG = {
    "host": os.getenv("PG_HOST", "localhost"),
    "port": int(os.getenv("PG_PORT", "5433")),
    "dbname": os.getenv("PG_DATABASE", "business_scoring"),
    "user": os.getenv("PG_USER", "postgres"),
    "password": os.getenv("PG_PASSWORD"),
}

NOW = datetime.now(timezone.utc)
TODAY = date.today()


def digits(length: int, start: int = 1) -> str:
    """Детерминированно генерирует цифры; это синтетические идентификаторы."""
    first = str(start % 10)
    return first + "".join(str(random.randint(0, 9)) for _ in range(length - 1))


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))


def insert_company(cur, i):
    is_legal = i % 2 == 1
    entity_type = "LEGAL_ENTITY" if is_legal else "INDIVIDUAL_ENTREPRENEUR"
    inn = digits(10 if is_legal else 12, start=i)
    ogrn = digits(13, start=i) if is_legal else None
    ogrnip = digits(15, start=i) if not is_legal else None
    registration_date = TODAY - timedelta(days=400 + i * 180)

    cur.execute(
        """
        INSERT INTO companies (
            entity_type, inn, ogrn, ogrnip, name, registration_date,
            status, status_date, okved_main, region_code, legal_address,
            director_name, director_authority_confirmed,
            information_reliability_status, source_checked_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING company_id
        """,
        (
            entity_type, inn, ogrn, ogrnip,
            f"ТЕСТОВАЯ КОМПАНИЯ {i:02d}" if is_legal else f"ТЕСТОВЫЙ ИП {i:02d}",
            registration_date, "ACTIVE", TODAY, random.choice(["41.20", "46.90", "47.11", "49.41"]),
            random.choice(["77", "78", "50", "66"]),
            f"Тестовый адрес, дом {i}",
            f"Тестовый руководитель {i:02d}" if is_legal else None,
            True if is_legal else None,
            "VERIFIED", NOW,
        ),
    )
    return cur.fetchone()[0]


def insert_financials(cur, company_id, i):
    base_revenue = 1_500_000 + i * 275_000
    for year_offset in (1, 0):
        end_year = TODAY.year - year_offset
        # Для текущего года создаём управленческую отчётность за последние 6 месяцев,
        # для прошлого — годовую. Периоды не пересекаются в рамках UNIQUE.
        if year_offset == 1:
            start, end, kind = date(end_year, 1, 1), date(end_year, 12, 31), "ANNUAL"
            revenue = base_revenue * 12
        else:
            start = TODAY - timedelta(days=180)
            end = TODAY
            kind = "MANAGEMENT"
            revenue = base_revenue * 6
        cost = revenue * 0.62
        operating = revenue * 0.18
        net = revenue * (0.06 if i % 4 == 0 else 0.10)
        assets = revenue * 0.55
        liabilities = revenue * 0.22
        cur.execute(
            """
            INSERT INTO financial_statements (
                company_id, period_start, period_end, statement_type, revenue,
                cost_of_sales, gross_profit, operating_expenses, operating_profit,
                net_profit, total_assets, current_assets, cash_and_equivalents,
                short_term_liabilities, total_liabilities, equity,
                source_document_id, source_checked_at, is_verified
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (company_id, period_start, period_end, statement_type) DO NOTHING
            """,
            (
                company_id, start, end, kind, money(revenue), money(cost),
                money(revenue - cost), money(revenue * 0.12), money(operating),
                money(net), money(assets), money(assets * 0.60), money(assets * 0.15),
                money(liabilities * 0.55), money(liabilities), money(assets - liabilities),
                f"SYNTHETIC-FS-{company_id}-{end_year}", NOW, True,
            ),
        )


def insert_transactions(cur, company_id, i):
    base = 80_000 + i * 12_500
    categories = [
        ("IN", "REVENUE", 1.0),
        ("OUT", "TAX", 0.12),
        ("OUT", "PAYROLL", 0.25),
        ("OUT", "RENT", 0.08),
        ("OUT", "OTHER", 0.18),
        ("IN", "REVENUE", 0.7),
    ]
    for j, (direction, category, factor) in enumerate(categories):
        amount = money(base * factor * random.uniform(0.75, 1.25))
        cur.execute(
            """
            INSERT INTO bank_transactions (
                company_id, account_ref, bank_name, transaction_date, amount,
                currency, direction, operation_category, counterparty_inn,
                counterparty_name, payment_purpose, balance_after,
                source_statement_id, source_checked_at
            )
            VALUES (%s,%s,%s,%s,%s,'RUB',%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                company_id, f"SYNTH-ACCOUNT-{company_id}", "Тестовый банк",
                NOW - timedelta(days=5 * (j + 1)), amount, direction, category,
                None, f"Синтетический контрагент {j + 1}",
                f"Тестовая операция: {category.lower()}",
                money(base * 2), f"SYNTH-TX-{company_id}-{j + 1}", NOW,
            ),
        )


def insert_application_and_risk_data(cur, company_id, i):
    product_code = ["R01", "R02", "R03"][(i - 1) % 3]
    amount = money(300_000 + i * 125_000)
    app_status = "SUBMITTED"
    missing_status = "PARTIAL" if i % 4 == 0 else "COMPLETE"

    cur.execute(
        """
        INSERT INTO credit_applications (
            company_id, product_code, application_date, requested_amount,
            requested_term_days, purpose, requested_monthly_payment,
            application_status, missing_data_status
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING application_id
        """,
        (
            company_id, product_code, NOW - timedelta(days=i),
            amount, 180 if product_code == "R01" else 365,
            "Пополнение оборотных средств (синтетическая заявка)",
            money(amount / 12), app_status, missing_status,
        ),
    )
    application_id = cur.fetchone()[0]

    # Небольшое текущее кредитное обязательство у части компаний.
    obligation_id = None
    if i % 3 != 0:
        overdue = i % 5 == 0
        cur.execute(
            """
            INSERT INTO credit_obligations (
                company_id, creditor_name, obligation_type, contract_ref,
                contract_date, maturity_date, original_amount, outstanding_balance,
                monthly_payment, interest_rate, overdue_amount, obligation_status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING obligation_id
            """,
            (
                company_id, "Синтетический кредитор", "LOAN",
                f"SYNTH-LOAN-{company_id}", TODAY - timedelta(days=300),
                TODAY + timedelta(days=400), money(500_000), money(180_000),
                money(25_000), Decimal("18.5000"),
                money(12_000 if overdue else 0), "OVERDUE" if overdue else "ACTIVE",
            ),
        )
        obligation_id = cur.fetchone()[0]
        if overdue:
            cur.execute(
                """
                INSERT INTO credit_history_events (
                    company_id, obligation_id, event_type, event_date,
                    overdue_days, overdue_amount, event_status, source_event_id,
                    source_checked_at
                )
                VALUES (%s,%s,'DELINQUENCY',%s,15,%s,'RESOLVED',%s,%s)
                """,
                (
                    company_id, obligation_id, TODAY - timedelta(days=60),
                    money(12_000), f"SYNTH-HISTORY-{company_id}", NOW,
                ),
            )

    if i % 4 == 0:
        cur.execute(
            """
            INSERT INTO legal_events (
                company_id, source_name, source_record_id, event_type,
                event_date, case_number, counterparty_name, amount,
                event_status, company_role, description, source_checked_at
            )
            VALUES (%s,'KAD',%s,'COURT_CASE',%s,%s,%s,%s,'CLOSED','DEFENDANT',%s,%s)
            """,
            (
                company_id, f"SYNTH-LEGAL-{company_id}", TODAY - timedelta(days=120),
                f"SYNTH-CASE-{company_id}", "Синтетический контрагент",
                money(35_000), "Искусственная тестовая запись, не реальное дело", NOW,
            ),
        )

    if missing_status != "COMPLETE":
        cur.execute(
            """
            INSERT INTO data_quality_checks (
                company_id, application_id, source_name, field_name, check_type,
                check_status, data_as_of, missing_fields, severity,
                resolution_status, resolution_comment
            )
            VALUES (%s,%s,%s,%s,'COMPLETENESS','WARNING',%s,%s,'MEDIUM','OPEN',%s)
            """,
            (
                company_id, application_id, "SYNTHETIC", "financial_statements",
                NOW, Jsonb(["interim_statement_confirmation"]),
                "Тест: требуется проверить полноту финансовых данных",
            ),
        )
    else:
        cur.execute(
            """
            INSERT INTO data_quality_checks (
                company_id, application_id, source_name, field_name, check_type,
                check_status, data_as_of, missing_fields, severity,
                resolution_status, resolution_comment
            )
            VALUES (%s,%s,%s,%s,'COMPLETENESS','PASS',%s,%s,'LOW','RESOLVED',%s)
            """,
            (
                company_id, application_id, "SYNTHETIC", "financial_statements",
                NOW, Jsonb([]),
                "Тест: обязательные тестовые поля заполнены",
            ),
        )

    # Синтетический пример результата модели. Это НЕ настоящая оценка риска.
    pd_value = Decimal("0.025000") if i % 4 else Decimal("0.120000")
    score = Decimal(str(round(800 - float(pd_value) * 1000 - i * 2, 4)))
    grade = "LOW" if pd_value < Decimal("0.05") else "HIGH"
    cur.execute(
        """
        INSERT INTO scoring_results (
            application_id, model_version, score, pd, risk_grade,
            feature_snapshot, source_snapshot_date
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING scoring_result_id
        """,
        (
            application_id, "synthetic-demo-v1", score, pd_value, grade,
            Jsonb({
                "synthetic_data": True,
                "revenue_6m_rub": int(1_500_000 + i * 275_000) * 6,
                "has_overdue_event": bool(i % 5 == 0),
                "note": "Демонстрационные значения; не использовать для кредитных решений",
            }),
            NOW,
        ),
    )
    scoring_result_id = cur.fetchone()[0]

    if missing_status != "COMPLETE":
        eligibility, decision = "NEEDS_DATA", "REQUEST_DATA"
        approved_amount, approved_term = None, None
        reasons = ["Синтетический сценарий: требуется уточнить данные"]
    elif grade == "HIGH":
        eligibility, decision = "ELIGIBLE", "MANUAL_REVIEW"
        approved_amount, approved_term = None, None
        reasons = ["Синтетический сценарий повышенного риска: ручная проверка"]
    else:
        eligibility, decision = "ELIGIBLE", "APPROVE"
        approved_amount, approved_term = amount, 180 if product_code == "R01" else 365
        reasons = ["Синтетический демонстрационный сценарий; не реальное решение"]

    cur.execute(
        """
        INSERT INTO credit_decisions (
            application_id, scoring_result_id, policy_version, eligibility_status,
            decision, approved_amount, approved_term_days, reasons
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            application_id, scoring_result_id, "synthetic-policy-v1", eligibility,
            decision, approved_amount, approved_term,
            Jsonb(reasons),
        ),
    )

    if product_code in ("R02", "R03"):
        cur.execute(
            """
            INSERT INTO credit_line_operations (
                company_id, application_id, product_code, operation_date,
                operation_type, operation_amount, credit_limit,
                outstanding_debt, available_limit, source_operation_id
            )
            VALUES (%s,%s,%s,%s,'DRAWDOWN',%s,%s,%s,%s,%s)
            """,
            (
                company_id, application_id, product_code, NOW - timedelta(days=2),
                money(amount * Decimal("0.20")), amount,
                money(amount * Decimal("0.20")), money(amount * Decimal("0.80")),
                f"SYNTH-LINE-OP-{application_id}",
            ),
        )

    return application_id


def main():
    if not DB_CONFIG["password"]:
        raise SystemExit(
            "Не задан пароль PostgreSQL. В PowerShell выполни:\n"
            '  $env:PG_PASSWORD = "ТВОЙ_ПАРОЛЬ_POSTGRES"\n'
            "Затем запусти: py seed_test_data.py"
        )

    with psycopg.connect(**DB_CONFIG) as conn:
        with conn.cursor() as cur:
            # Предотвращаем случайное повторное добавление одного и того же набора.
            cur.execute(
                "SELECT COUNT(*) FROM companies WHERE name LIKE 'ТЕСТОВАЯ КОМПАНИЯ %' "
                "OR name LIKE 'ТЕСТОВЫЙ ИП %'"
            )
            existing = cur.fetchone()[0]
            if existing:
                raise SystemExit(
                    f"В базе уже найдено {existing} синтетических компаний. "
                    "Скрипт остановлен, чтобы не создавать дубликаты. "
                    "Если нужно повторить тест, сначала обсудите очистку тестовых данных."
                )

            company_ids = []
            for i in range(1, 11):
                company_id = insert_company(cur, i)
                company_ids.append(company_id)
                insert_financials(cur, company_id, i)
                insert_transactions(cur, company_id, i)
                insert_application_and_risk_data(cur, company_id, i)

        conn.commit()

    print("Готово! Добавлены синтетические тестовые данные.")
    print("Ожидается: 10 компаний, 20 финансовых записей, 60 транзакций,")
    print("10 заявок, тестовые кредитные обязательства/события,")
    print("10 результатов скоринга, 10 решений и проверки качества данных.")
    print("ВАЖНО: оценки PD, score и решения искусственные — только для проверки схемы.")


if __name__ == "__main__":
    main()
