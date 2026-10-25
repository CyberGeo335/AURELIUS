ALTER TABLE aurelius_agent_v2.audit ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}';
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.security_audit (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    actor_id TEXT NOT NULL,
    company_id BIGINT NOT NULL,
    action TEXT NOT NULL,
    scope TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
