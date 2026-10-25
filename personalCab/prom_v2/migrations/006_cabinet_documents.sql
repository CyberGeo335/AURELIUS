-- Real document bytes and provenance; no financial extraction or public DDL.
CREATE TABLE IF NOT EXISTS aurelius_cabinet.documents (
    document_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    uploaded_by BIGINT NOT NULL REFERENCES public.user_accounts(user_id),
    data_request_id BIGINT REFERENCES public.application_data_requests(request_id),
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('application/pdf', 'text/csv')),
    content BYTEA NOT NULL CHECK (octet_length(content) BETWEEN 1 AND 10485760),
    sha256 TEXT NOT NULL,
    source TEXT NOT NULL CHECK (source IN ('CLIENT_UPLOAD', 'EMPLOYEE_UPLOAD')),
    processing_status TEXT NOT NULL DEFAULT 'STORED_UNVERIFIED'
        CHECK (processing_status = 'STORED_UNVERIFIED'),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS documents_application_idx ON aurelius_cabinet.documents(application_id);
