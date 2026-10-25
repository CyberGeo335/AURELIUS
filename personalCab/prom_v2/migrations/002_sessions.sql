CREATE TABLE IF NOT EXISTS aurelius_agent_v2.accounts (
 login TEXT PRIMARY KEY, password_hash TEXT NOT NULL,full_name TEXT NOT NULL,
 role TEXT NOT NULL CHECK(role IN ('BORROWER','OPERATOR')),company_id BIGINT REFERENCES public.companies(company_id),active BOOLEAN NOT NULL DEFAULT true,
 CHECK ((role='BORROWER' AND company_id IS NOT NULL) OR role='OPERATOR'));
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.sessions(token_hash TEXT PRIMARY KEY,login TEXT NOT NULL REFERENCES aurelius_agent_v2.accounts(login),expires_at TIMESTAMPTZ NOT NULL);
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.login_attempts(address TEXT NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.grants(login TEXT NOT NULL REFERENCES aurelius_agent_v2.accounts(login),scope TEXT NOT NULL,granted_at TIMESTAMPTZ NOT NULL,expires_at TIMESTAMPTZ NOT NULL,revoked BOOLEAN NOT NULL,PRIMARY KEY(login,scope));
CREATE TABLE IF NOT EXISTS aurelius_agent_v2.action_receipts(login TEXT NOT NULL,request_id TEXT NOT NULL,input_hash TEXT NOT NULL,result JSONB NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT now(),PRIMARY KEY(login,request_id));
