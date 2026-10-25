CREATE TABLE IF NOT EXISTS aurelius_cabinet.dialogues (
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    company_id BIGINT NOT NULL REFERENCES public.companies(company_id),
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY(application_id,user_id)
);
