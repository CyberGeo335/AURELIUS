-- Client identity is assigned only after password authentication.
CREATE TABLE IF NOT EXISTS aurelius_workflow.client_accounts (
 client_id TEXT PRIMARY KEY, full_name TEXT NOT NULL,
 login TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
 company_id BIGINT NOT NULL UNIQUE REFERENCES public.companies(company_id),
 active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS aurelius_workflow.client_sessions (
 token TEXT PRIMARY KEY REFERENCES aurelius_workflow.web_clients(token) ON DELETE CASCADE,
 client_id TEXT NOT NULL REFERENCES aurelius_workflow.client_accounts(client_id),
 expires_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS aurelius_workflow.client_field_changes (
 change_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 case_id TEXT NOT NULL, revision INTEGER NOT NULL, company_id BIGINT NOT NULL,
 product_code TEXT NOT NULL, field_code TEXT NOT NULL,
 old_value JSONB, new_value JSONB, changed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 review_status TEXT NOT NULL DEFAULT 'PENDING', reviewed_by TEXT, source_ref TEXT);
