-- Explicit V2-only bootstrap. No V1 workflow or public business rows are modified.
CREATE SCHEMA IF NOT EXISTS aurelius_agent_v2;
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.cases (
    case_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    company_id BIGINT NOT NULL CHECK (company_id > 0),
    borrower_id TEXT NOT NULL,
    version BIGINT NOT NULL CHECK (version > 0),
    payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS agent_v2_case_owner ON aurelius_agent_v2.cases(owner_id, company_id, borrower_id);
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.receipts (
    owner_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    case_id TEXT NOT NULL REFERENCES aurelius_agent_v2.cases(case_id),
    result JSONB NOT NULL,
    PRIMARY KEY (owner_id, request_id)
);
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES aurelius_agent_v2.cases(case_id),
    version BIGINT NOT NULL,
    revision BIGINT NOT NULL,
    actor_id TEXT NOT NULL,
    action TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (case_id, version)
);
