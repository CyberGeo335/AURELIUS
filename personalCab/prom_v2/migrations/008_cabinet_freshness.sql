CREATE TABLE IF NOT EXISTS aurelius_cabinet.calculation_inputs (
    input_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    snapshot_id BIGINT NOT NULL REFERENCES public.application_snapshots(snapshot_id),
    input_hash TEXT NOT NULL,
    offer_hash TEXT,
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS aurelius_cabinet.offer_publications (
    offer_id BIGINT PRIMARY KEY REFERENCES public.application_product_terms(offer_id),
    input_id BIGINT NOT NULL REFERENCES aurelius_cabinet.calculation_inputs(input_id),
    decision_id BIGINT NOT NULL REFERENCES public.credit_decisions(decision_id),
    offer_hash TEXT NOT NULL,
    published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS aurelius_cabinet.stale_offers (
    offer_id BIGINT PRIMARY KEY REFERENCES public.application_product_terms(offer_id),
    application_id BIGINT NOT NULL REFERENCES public.credit_applications(application_id),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason TEXT NOT NULL
);
