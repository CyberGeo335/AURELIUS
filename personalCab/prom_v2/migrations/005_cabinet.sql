-- Additive cabinet metadata. Never alters public v3 tables or existing FKs.
CREATE SCHEMA IF NOT EXISTS aurelius_cabinet;
CREATE TABLE IF NOT EXISTS aurelius_cabinet.sessions (
    token_hash TEXT PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    expires_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE IF NOT EXISTS aurelius_cabinet.application_state (
    application_id BIGINT PRIMARY KEY REFERENCES public.credit_applications(application_id),
    version INTEGER NOT NULL DEFAULT 1,
    form_state JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS aurelius_cabinet.receipts (
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    request_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    result JSONB NOT NULL,
    PRIMARY KEY(user_id, request_id)
);
CREATE TABLE IF NOT EXISTS aurelius_cabinet.events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    user_id BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    action TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
