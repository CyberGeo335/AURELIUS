CREATE TABLE IF NOT EXISTS aurelius_cabinet.assignments (
    application_id BIGINT PRIMARY KEY REFERENCES public.credit_applications(application_id),
    employee_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS assignments_employee_idx ON aurelius_cabinet.assignments(employee_id);
