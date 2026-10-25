CREATE TABLE IF NOT EXISTS aurelius_agent_v2.pending_operations (
    login TEXT NOT NULL REFERENCES aurelius_agent_v2.accounts(login),
    request_id TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    body JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (login, request_id)
);
