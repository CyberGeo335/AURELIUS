-- Additive M1--M5 DEMO services. Existing business rows are preserved.
CREATE TABLE IF NOT EXISTS aurelius_workflow.web_profiles (
 actor_id TEXT PRIMARY KEY, company_id BIGINT REFERENCES public.companies(company_id));
CREATE TABLE IF NOT EXISTS aurelius_workflow.consents (
 actor_id TEXT NOT NULL, company_id BIGINT NOT NULL REFERENCES public.companies(company_id),
 scope TEXT NOT NULL, granted_at TIMESTAMPTZ NOT NULL, expires_at TIMESTAMPTZ NOT NULL,
 revoked_at TIMESTAMPTZ, PRIMARY KEY(actor_id,company_id,scope));
CREATE TABLE IF NOT EXISTS aurelius_workflow.control_receipts (
 actor_id TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL, payload TEXT NOT NULL,
 PRIMARY KEY(actor_id,request_id));
CREATE TABLE IF NOT EXISTS aurelius_workflow.evidence_documents (
 document_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES aurelius_workflow.credit_cases(case_id),
 owner_id TEXT NOT NULL, company_id BIGINT NOT NULL REFERENCES public.companies(company_id),
 filename TEXT NOT NULL, content_type TEXT NOT NULL, sha256 TEXT NOT NULL, content BYTEA NOT NULL,
 extracted_data JSONB NOT NULL, uploaded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(case_id,sha256));
CREATE TABLE IF NOT EXISTS aurelius_workflow.feature_inputs (
 input_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES aurelius_workflow.credit_cases(case_id),
 revision INTEGER NOT NULL, evidence_ref TEXT NOT NULL, product_code VARCHAR(10) NOT NULL,
 data JSONB NOT NULL, reviewed_by TEXT NOT NULL, reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(case_id,revision,evidence_ref,product_code));
CREATE TABLE IF NOT EXISTS aurelius_workflow.assessments (
 assessment_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES aurelius_workflow.credit_cases(case_id),
 revision INTEGER NOT NULL, evidence_ref TEXT NOT NULL, product_code VARCHAR(10) NOT NULL,
 input_hash TEXT NOT NULL, data JSONB NOT NULL, scoring_result_id BIGINT REFERENCES public.scoring_results(scoring_result_id),
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE(case_id,revision,product_code,input_hash));
CREATE TABLE IF NOT EXISTS aurelius_workflow.lender_cases (
 lender_case_id TEXT PRIMARY KEY, case_id TEXT NOT NULL REFERENCES aurelius_workflow.credit_cases(case_id),
 revision INTEGER NOT NULL, product_code VARCHAR(10) NOT NULL, evidence_ref TEXT NOT NULL,
 data JSONB NOT NULL, version INTEGER NOT NULL DEFAULT 1,
 UNIQUE(case_id,revision,product_code));
CREATE TABLE IF NOT EXISTS aurelius_workflow.lender_events (
 event_id TEXT PRIMARY KEY, lender_case_id TEXT NOT NULL REFERENCES aurelius_workflow.lender_cases(lender_case_id),
 event_type TEXT NOT NULL, actor_id TEXT NOT NULL, data JSONB NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS aurelius_workflow.product_approvals (
 terms_id BIGINT PRIMARY KEY REFERENCES public.credit_product_terms(terms_id),
 policy_version TEXT NOT NULL, approved_by TEXT NOT NULL, approved_at TIMESTAMPTZ NOT NULL,
 -- Only rule mappings explicitly reviewed by the operator are executable.
 rule_mappings JSONB NOT NULL DEFAULT '{}'::jsonb);
CREATE TABLE IF NOT EXISTS aurelius_workflow.profile_resolutions (
 resolution_id TEXT PRIMARY KEY, company_id BIGINT NOT NULL REFERENCES public.companies(company_id),
 legal_form TEXT NOT NULL CHECK(legal_form IN ('IP','OOO','AO','OTHER')), source_ref TEXT NOT NULL,
 available_at TIMESTAMPTZ NOT NULL, reviewed_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
 reviewed_by TEXT NOT NULL);
