-- Synthetic DEMO history only. Run with psql -v ON_ERROR_STOP=1.
-- November 2025 already has RUB 1,200,000 revenue per company in v3.
-- Add the same synthetic monthly amount for September and October 2025.
BEGIN;
SET LOCAL TIME ZONE 'UTC';
LOCK TABLE public.bank_transactions IN SHARE ROW EXCLUSIVE MODE;

CREATE TEMP TABLE revenue_backfill_companies ON COMMIT DROP AS
SELECT DISTINCT company_id, account_ref, bank_name
FROM public.bank_transactions
WHERE account_ref ~ '^AURELIUS_DEMO_20261024-[0-9]{2}$'
  AND bank_name = 'AURELIUS DEMO BANK';

DO $$
BEGIN
    IF (SELECT count(*) FROM revenue_backfill_companies) <> 30
       OR (SELECT count(DISTINCT company_id) FROM revenue_backfill_companies) <> 30
    THEN
        RAISE EXCEPTION 'Expected exactly 30 seeded DEMO companies/accounts';
    END IF;
END $$;

INSERT INTO public.bank_transactions (
    company_id, account_ref, bank_name, transaction_date, amount, currency,
    direction, operation_category, payment_purpose, source_statement_id,
    source_checked_at
)
SELECT c.company_id, c.account_ref, c.bank_name,
       m.month_start + INTERVAL '14 days', 1200000.00, 'RUB', 'IN', 'REVENUE',
       'Синтетическая выручка DEMO за ' || to_char(m.month_start, 'YYYY-MM'),
       c.account_ref || '-REVENUE-' || to_char(m.month_start, 'YYYY-MM'),
       CURRENT_TIMESTAMP
FROM revenue_backfill_companies AS c
CROSS JOIN (VALUES (TIMESTAMPTZ '2025-09-01 00:00:00+00'),
                   (TIMESTAMPTZ '2025-10-01 00:00:00+00')) AS m(month_start)
WHERE NOT EXISTS (
    SELECT 1 FROM public.bank_transactions AS t
    WHERE t.company_id = c.company_id
      AND t.transaction_date >= m.month_start
      AND t.transaction_date < m.month_start + INTERVAL '1 month'
      AND t.direction = 'IN' AND t.operation_category = 'REVENUE'
      AND t.currency = 'RUB' AND t.amount > 0
);

DO $$
BEGIN
    IF (
        SELECT count(*) FROM (
            SELECT c.company_id, date_trunc('month', t.transaction_date)
            FROM revenue_backfill_companies AS c
            JOIN public.bank_transactions AS t USING (company_id)
            WHERE t.transaction_date >= TIMESTAMPTZ '2025-09-01 00:00:00+00'
              AND t.transaction_date < TIMESTAMPTZ '2025-11-01 00:00:00+00'
              AND t.direction = 'IN' AND t.operation_category = 'REVENUE'
              AND t.currency = 'RUB' AND t.amount > 0
            GROUP BY c.company_id, date_trunc('month', t.transaction_date)
        ) AS covered_months
    ) <> 60 THEN
        RAISE EXCEPTION 'Expected positive RUB revenue for 30 companies in both months';
    END IF;
END $$;
COMMIT;
