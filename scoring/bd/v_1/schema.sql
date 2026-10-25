--
-- PostgreSQL database dump
--

\restrict BvCZ5uGGSdxi1KYjmftb2p4JJWy0ZT2ydyIaS5AaqoHu1zZ0L7uWrUIeguqyy8U

-- Dumped from database version 17.11
-- Dumped by pg_dump version 18.4

-- Started on 2026-10-23 23:59:10

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- TOC entry 282 (class 1255 OID 19814)
-- Name: aurelius_log_field_change(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.aurelius_log_field_change() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 IF TG_OP = 'INSERT' THEN
   INSERT INTO application_field_history(application_id, product_code, field_code, old_value, new_value, changed_by_type, source_type, source_reference, verification_status)
   VALUES(NEW.application_id, NEW.product_code, NEW.field_code, NULL, NEW.field_value, NEW.changed_by_type, COALESCE(NEW.value_source,'OTHER'), NEW.source_reference, COALESCE(NEW.verification_status,'UNVERIFIED'));
   RETURN NEW;
 ELSIF TG_OP = 'UPDATE' THEN
   IF (OLD.field_value, OLD.value_source, OLD.source_reference, OLD.verification_status) IS DISTINCT FROM
      (NEW.field_value, NEW.value_source, NEW.source_reference, NEW.verification_status) THEN
     INSERT INTO application_field_history(application_id, product_code, field_code, old_value, new_value, changed_by_type, source_type, source_reference, verification_status)
     VALUES(NEW.application_id, NEW.product_code, NEW.field_code, OLD.field_value, NEW.field_value, NEW.changed_by_type, COALESCE(NEW.value_source,'OTHER'), NEW.source_reference, COALESCE(NEW.verification_status,'UNVERIFIED'));
   END IF;
   RETURN NEW;
 ELSE
   INSERT INTO application_field_history(application_id, product_code, field_code, old_value, new_value, changed_by_type, source_type, source_reference, verification_status)
   VALUES(OLD.application_id, OLD.product_code, OLD.field_code, OLD.field_value, NULL, OLD.changed_by_type, COALESCE(OLD.value_source,'OTHER'), OLD.source_reference, COALESCE(OLD.verification_status,'UNVERIFIED'));
   RETURN OLD;
 END IF;
END;
$$;


--
-- TOC entry 283 (class 1255 OID 19816)
-- Name: aurelius_reject_history_mutation(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.aurelius_reject_history_mutation() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
 RAISE EXCEPTION 'Immutable audit record: UPDATE and DELETE are not allowed';
END;
$$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- TOC entry 271 (class 1259 OID 19629)
-- Name: application_data_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_data_requests (
    request_id bigint NOT NULL,
    application_id bigint NOT NULL,
    product_code character varying(10) NOT NULL,
    field_code text NOT NULL,
    question_text text NOT NULL,
    request_status character varying(20) DEFAULT 'OPEN'::character varying NOT NULL,
    requested_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    answered_at timestamp with time zone,
    answer_value jsonb,
    CONSTRAINT application_data_requests_request_status_check CHECK (((request_status)::text = ANY ((ARRAY['OPEN'::character varying, 'ANSWERED'::character varying, 'CANCELLED'::character varying])::text[])))
);


--
-- TOC entry 270 (class 1259 OID 19628)
-- Name: application_data_requests_request_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.application_data_requests ALTER COLUMN request_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.application_data_requests_request_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 248 (class 1259 OID 19398)
-- Name: application_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_details (
    application_id bigint NOT NULL,
    guarantor_participation boolean,
    proposed_collateral boolean,
    contact_full_name text,
    contact_role text,
    contact_phone text,
    signer_full_name text,
    signer_authority_basis text,
    confirmation_version text,
    confirmed_at timestamp with time zone
);


--
-- TOC entry 277 (class 1259 OID 19703)
-- Name: application_field_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_field_history (
    history_id bigint NOT NULL,
    application_id bigint NOT NULL,
    product_code character varying(10) NOT NULL,
    field_code text NOT NULL,
    old_value jsonb,
    new_value jsonb,
    changed_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    changed_by_type character varying(20) NOT NULL,
    source_type character varying(20) NOT NULL,
    source_reference text,
    verification_status character varying(20) DEFAULT 'UNVERIFIED'::character varying NOT NULL,
    CONSTRAINT application_field_history_changed_by_type_check CHECK (((changed_by_type)::text = ANY ((ARRAY['CLIENT'::character varying, 'BANK'::character varying, 'SYSTEM'::character varying, 'LLM'::character varying])::text[]))),
    CONSTRAINT application_field_history_source_type_check CHECK (((source_type)::text = ANY ((ARRAY['BANK'::character varying, 'FNS'::character varying, 'SME_REGISTER'::character varying, 'BKI'::character varying, 'CLIENT'::character varying, 'CALCULATED'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT application_field_history_verification_status_check CHECK (((verification_status)::text = ANY ((ARRAY['VERIFIED'::character varying, 'UNVERIFIED'::character varying, 'CONFLICT'::character varying, 'EXPIRED'::character varying])::text[])))
);


--
-- TOC entry 276 (class 1259 OID 19702)
-- Name: application_field_history_history_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.application_field_history ALTER COLUMN history_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.application_field_history_history_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 249 (class 1259 OID 19410)
-- Name: application_field_requirements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_field_requirements (
    product_code character varying(10) NOT NULL,
    field_number integer NOT NULL,
    field_code text NOT NULL,
    field_label text NOT NULL,
    required_ip boolean NOT NULL,
    required_ooo boolean NOT NULL,
    format_rule text,
    source_description text,
    fill_method text,
    target_db_field text NOT NULL
);


--
-- TOC entry 250 (class 1259 OID 19424)
-- Name: application_field_values; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_field_values (
    application_id bigint NOT NULL,
    field_code text NOT NULL,
    field_value jsonb,
    value_source character varying(20),
    source_reference text,
    obtained_at timestamp with time zone,
    verification_status character varying(20),
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    changed_by_type character varying(20) DEFAULT 'SYSTEM'::character varying NOT NULL,
    product_code character varying(10) NOT NULL,
    CONSTRAINT application_field_values_changed_by_type_check CHECK (((changed_by_type)::text = ANY ((ARRAY['CLIENT'::character varying, 'BANK'::character varying, 'SYSTEM'::character varying, 'LLM'::character varying])::text[]))),
    CONSTRAINT application_field_values_value_source_check CHECK (((value_source IS NULL) OR ((value_source)::text = ANY ((ARRAY['BANK'::character varying, 'FNS'::character varying, 'SME_REGISTER'::character varying, 'BKI'::character varying, 'CLIENT'::character varying, 'CALCULATED'::character varying, 'OTHER'::character varying])::text[])))),
    CONSTRAINT application_field_values_verification_status_check CHECK (((verification_status IS NULL) OR ((verification_status)::text = ANY ((ARRAY['VERIFIED'::character varying, 'UNVERIFIED'::character varying, 'CONFLICT'::character varying, 'EXPIRED'::character varying])::text[]))))
);


--
-- TOC entry 255 (class 1259 OID 19473)
-- Name: application_product_details; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_product_details (
    application_id bigint NOT NULL,
    max_tranche_term_value integer,
    max_tranche_term_unit character varying(10),
    drawdown_start_date date,
    drawdown_end_date date,
    drawdown_period_months integer,
    is_revolving boolean,
    overdraft_bank_account_id bigint,
    overdraft_account_ref character varying(20),
    overdraft_bank_name text,
    overdraft_bank_bik character varying(9),
    company_id bigint NOT NULL,
    CONSTRAINT application_product_details_check CHECK (((drawdown_start_date IS NULL) OR (drawdown_end_date IS NULL) OR (drawdown_end_date >= drawdown_start_date))),
    CONSTRAINT application_product_details_drawdown_period_months_check CHECK (((drawdown_period_months IS NULL) OR (drawdown_period_months > 0))),
    CONSTRAINT application_product_details_max_tranche_term_unit_check CHECK (((max_tranche_term_unit IS NULL) OR ((max_tranche_term_unit)::text = ANY ((ARRAY['DAYS'::character varying, 'MONTHS'::character varying])::text[])))),
    CONSTRAINT application_product_details_max_tranche_term_value_check CHECK (((max_tranche_term_value IS NULL) OR (max_tranche_term_value > 0))),
    CONSTRAINT application_product_details_overdraft_account_ref_check CHECK (((overdraft_account_ref IS NULL) OR ((overdraft_account_ref)::text ~ '^[0-9]{20}$'::text))),
    CONSTRAINT application_product_details_overdraft_bank_bik_check CHECK (((overdraft_bank_bik IS NULL) OR ((overdraft_bank_bik)::text ~ '^[0-9]{9}$'::text)))
);


--
-- TOC entry 273 (class 1259 OID 19645)
-- Name: application_product_terms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_product_terms (
    offer_id bigint NOT NULL,
    application_id bigint NOT NULL,
    terms_id bigint NOT NULL,
    rate_option_id bigint,
    repayment_option_id bigint,
    offered_amount numeric(18,2),
    offered_term_months integer,
    offered_annual_rate_pct numeric(9,4),
    offered_tranche_term_value integer,
    offered_tranche_term_unit character varying(10),
    offered_drawdown_period_months integer,
    offered_service_cost numeric(18,2),
    offered_fees jsonb,
    offered_conditions jsonb,
    product_code character varying(10) NOT NULL,
    offer_status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT application_product_terms_offer_status_check CHECK (((offer_status)::text = ANY ((ARRAY['DRAFT'::character varying, 'PROPOSED'::character varying, 'ACCEPTED'::character varying, 'DECLINED'::character varying])::text[]))),
    CONSTRAINT application_product_terms_offered_amount_check CHECK (((offered_amount IS NULL) OR (offered_amount >= (0)::numeric))),
    CONSTRAINT application_product_terms_offered_annual_rate_pct_check CHECK (((offered_annual_rate_pct IS NULL) OR (offered_annual_rate_pct >= (0)::numeric))),
    CONSTRAINT application_product_terms_offered_drawdown_period_months_check CHECK (((offered_drawdown_period_months IS NULL) OR (offered_drawdown_period_months > 0))),
    CONSTRAINT application_product_terms_offered_service_cost_check CHECK (((offered_service_cost IS NULL) OR (offered_service_cost >= (0)::numeric))),
    CONSTRAINT application_product_terms_offered_term_months_check CHECK (((offered_term_months IS NULL) OR (offered_term_months > 0))),
    CONSTRAINT application_product_terms_offered_tranche_term_unit_check CHECK (((offered_tranche_term_unit IS NULL) OR ((offered_tranche_term_unit)::text = ANY ((ARRAY['DAYS'::character varying, 'MONTHS'::character varying])::text[])))),
    CONSTRAINT application_product_terms_offered_tranche_term_value_check CHECK (((offered_tranche_term_value IS NULL) OR (offered_tranche_term_value > 0)))
);


--
-- TOC entry 272 (class 1259 OID 19644)
-- Name: application_product_terms_offer_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.application_product_terms ALTER COLUMN offer_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.application_product_terms_offer_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 275 (class 1259 OID 19683)
-- Name: application_snapshots; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.application_snapshots (
    snapshot_id bigint NOT NULL,
    application_id bigint NOT NULL,
    snapshot_type character varying(20) NOT NULL,
    snapshot_data jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    created_by_type character varying(20) NOT NULL,
    snapshot_version integer NOT NULL,
    CONSTRAINT application_snapshots_created_by_type_check CHECK (((created_by_type)::text = ANY ((ARRAY['CLIENT'::character varying, 'BANK'::character varying, 'SYSTEM'::character varying, 'LLM'::character varying])::text[]))),
    CONSTRAINT application_snapshots_snapshot_data_check CHECK ((jsonb_typeof(snapshot_data) = 'object'::text)),
    CONSTRAINT application_snapshots_snapshot_type_check CHECK (((snapshot_type)::text = ANY ((ARRAY['SUBMISSION'::character varying, 'DECISION'::character varying, 'MANUAL'::character varying])::text[]))),
    CONSTRAINT application_snapshots_snapshot_version_check CHECK ((snapshot_version > 0))
);


--
-- TOC entry 274 (class 1259 OID 19682)
-- Name: application_snapshots_snapshot_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.application_snapshots ALTER COLUMN snapshot_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.application_snapshots_snapshot_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 222 (class 1259 OID 19090)
-- Name: bank_transactions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.bank_transactions (
    transaction_id bigint NOT NULL,
    company_id bigint NOT NULL,
    account_ref character varying(100),
    bank_name character varying(100),
    transaction_date timestamp with time zone NOT NULL,
    amount numeric(18,2) NOT NULL,
    currency character(3) DEFAULT 'RUB'::bpchar NOT NULL,
    direction character varying(10) NOT NULL,
    operation_category character varying(30) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    counterparty_inn character varying(12),
    counterparty_name text,
    payment_purpose text,
    balance_after numeric(18,2),
    source_statement_id character varying(100),
    source_checked_at timestamp with time zone,
    CONSTRAINT bank_transactions_amount_check CHECK ((amount >= (0)::numeric)),
    CONSTRAINT bank_transactions_direction_check CHECK (((direction)::text = ANY ((ARRAY['IN'::character varying, 'OUT'::character varying])::text[]))),
    CONSTRAINT bank_transactions_operation_category_check CHECK (((operation_category)::text = ANY ((ARRAY['REVENUE'::character varying, 'TAX'::character varying, 'PAYROLL'::character varying, 'RENT'::character varying, 'LOAN'::character varying, 'INTERNAL_TRANSFER'::character varying, 'REFUND'::character varying, 'OTHER'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- TOC entry 221 (class 1259 OID 19089)
-- Name: bank_transactions_transaction_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.bank_transactions ALTER COLUMN transaction_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.bank_transactions_transaction_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 237 (class 1259 OID 19249)
-- Name: collateral; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.collateral (
    collateral_id bigint NOT NULL,
    company_id bigint NOT NULL,
    application_id bigint NOT NULL,
    asset_type character varying(20) NOT NULL,
    asset_description text,
    owner_type character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    owner_ref text,
    estimated_market_value numeric(18,2),
    valuation_date date,
    discount_rate numeric(6,4),
    estimated_liquidation_value numeric(18,2),
    encumbrance_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    registry_name character varying(50),
    registry_record_id text,
    verification_date timestamp with time zone,
    collateral_status character varying(20) DEFAULT 'PENDING'::character varying NOT NULL,
    CONSTRAINT collateral_asset_type_check CHECK (((asset_type)::text = ANY ((ARRAY['REAL_ESTATE'::character varying, 'VEHICLE'::character varying, 'EQUIPMENT'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT collateral_collateral_status_check CHECK (((collateral_status)::text = ANY ((ARRAY['PENDING'::character varying, 'VERIFIED'::character varying, 'REJECTED'::character varying, 'RELEASED'::character varying])::text[]))),
    CONSTRAINT collateral_discount_rate_check CHECK (((discount_rate IS NULL) OR ((discount_rate >= (0)::numeric) AND (discount_rate <= (1)::numeric)))),
    CONSTRAINT collateral_encumbrance_status_check CHECK (((encumbrance_status)::text = ANY ((ARRAY['NONE'::character varying, 'PRESENT'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT collateral_estimated_liquidation_value_check CHECK (((estimated_liquidation_value IS NULL) OR (estimated_liquidation_value >= (0)::numeric))),
    CONSTRAINT collateral_estimated_market_value_check CHECK (((estimated_market_value IS NULL) OR (estimated_market_value >= (0)::numeric))),
    CONSTRAINT collateral_owner_type_check CHECK (((owner_type)::text = ANY ((ARRAY['COMPANY'::character varying, 'OWNER'::character varying, 'THIRD_PARTY'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- TOC entry 236 (class 1259 OID 19248)
-- Name: collateral_collateral_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.collateral ALTER COLUMN collateral_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.collateral_collateral_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 220 (class 1259 OID 19069)
-- Name: companies; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.companies (
    company_id bigint NOT NULL,
    entity_type character varying(30) NOT NULL,
    inn character varying(12) NOT NULL,
    ogrn character varying(13),
    ogrnip character varying(15),
    name text NOT NULL,
    registration_date date,
    status character varying(30) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    status_date date,
    okved_main character varying(10),
    region_code character varying(10),
    legal_address text,
    director_name text,
    director_authority_confirmed boolean,
    information_reliability_status character varying(30) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    source_checked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    kpp character varying(9),
    legal_form text,
    okved_main_name text,
    actual_activity_description text,
    actual_business_address text,
    business_region text,
    business_city text,
    sme_category character varying(20),
    actual_activity_start_date date,
    director_position text,
    CONSTRAINT companies_check CHECK (((((entity_type)::text = 'LEGAL_ENTITY'::text) AND (ogrn IS NOT NULL) AND (ogrnip IS NULL) AND (length((inn)::text) = 10)) OR (((entity_type)::text = 'INDIVIDUAL_ENTREPRENEUR'::text) AND (ogrnip IS NOT NULL) AND (ogrn IS NULL) AND (length((inn)::text) = 12)))),
    CONSTRAINT companies_entity_type_check CHECK (((entity_type)::text = ANY ((ARRAY['LEGAL_ENTITY'::character varying, 'INDIVIDUAL_ENTREPRENEUR'::character varying])::text[]))),
    CONSTRAINT companies_information_reliability_status_check CHECK (((information_reliability_status)::text = ANY ((ARRAY['VERIFIED'::character varying, 'UNVERIFIED'::character varying, 'CONFLICT'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT companies_inn_check CHECK ((((inn)::text ~ '^[0-9]{10}$'::text) OR ((inn)::text ~ '^[0-9]{12}$'::text))),
    CONSTRAINT companies_ogrn_check CHECK (((ogrn IS NULL) OR ((ogrn)::text ~ '^[0-9]{13}$'::text))),
    CONSTRAINT companies_ogrnip_check CHECK (((ogrnip IS NULL) OR ((ogrnip)::text ~ '^[0-9]{15}$'::text))),
    CONSTRAINT companies_status_check CHECK (((status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'LIQUIDATING'::character varying, 'INACTIVE'::character varying, 'BANKRUPTCY'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- TOC entry 219 (class 1259 OID 19068)
-- Name: companies_company_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.companies ALTER COLUMN company_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.companies_company_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 252 (class 1259 OID 19442)
-- Name: company_bank_accounts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_bank_accounts (
    account_id bigint NOT NULL,
    company_id bigint NOT NULL,
    account_number character varying(20) NOT NULL,
    bank_name text NOT NULL,
    bank_bik character varying(9),
    account_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    source_checked_at timestamp with time zone,
    CONSTRAINT company_bank_accounts_account_number_check CHECK (((account_number)::text ~ '^[0-9]{20}$'::text)),
    CONSTRAINT company_bank_accounts_account_status_check CHECK (((account_status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'CLOSED'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT company_bank_accounts_bank_bik_check CHECK (((bank_bik IS NULL) OR ((bank_bik)::text ~ '^[0-9]{9}$'::text)))
);


--
-- TOC entry 251 (class 1259 OID 19441)
-- Name: company_bank_accounts_account_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.company_bank_accounts ALTER COLUMN account_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.company_bank_accounts_account_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 254 (class 1259 OID 19461)
-- Name: company_contacts; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_contacts (
    contact_id bigint NOT NULL,
    company_id bigint NOT NULL,
    full_name text NOT NULL,
    contact_role text,
    phone text,
    authority_basis text,
    is_current boolean,
    source_checked_at timestamp with time zone
);


--
-- TOC entry 253 (class 1259 OID 19460)
-- Name: company_contacts_contact_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.company_contacts ALTER COLUMN contact_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.company_contacts_contact_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 269 (class 1259 OID 19611)
-- Name: company_data_provenance; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.company_data_provenance (
    provenance_id bigint NOT NULL,
    company_id bigint NOT NULL,
    target_table text NOT NULL,
    target_record_pk jsonb NOT NULL,
    target_field text NOT NULL,
    observed_value jsonb,
    source_type character varying(30) NOT NULL,
    source_reference text,
    obtained_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    verification_status character varying(20) DEFAULT 'UNVERIFIED'::character varying NOT NULL,
    verified_at timestamp with time zone,
    CONSTRAINT company_data_provenance_source_type_check CHECK (((source_type)::text = ANY ((ARRAY['BANK'::character varying, 'FNS'::character varying, 'SME_REGISTER'::character varying, 'BKI'::character varying, 'CLIENT'::character varying, 'CALCULATED'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT company_data_provenance_target_record_pk_check CHECK ((jsonb_typeof(target_record_pk) = 'object'::text)),
    CONSTRAINT company_data_provenance_verification_status_check CHECK (((verification_status)::text = ANY ((ARRAY['VERIFIED'::character varying, 'UNVERIFIED'::character varying, 'CONFLICT'::character varying, 'EXPIRED'::character varying])::text[])))
);


--
-- TOC entry 268 (class 1259 OID 19610)
-- Name: company_data_provenance_provenance_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.company_data_provenance ALTER COLUMN provenance_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.company_data_provenance_provenance_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 235 (class 1259 OID 19223)
-- Name: credit_applications; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_applications (
    application_id bigint NOT NULL,
    company_id bigint NOT NULL,
    product_code character varying(10) NOT NULL,
    application_date timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    requested_amount numeric(18,2),
    requested_term_days integer,
    purpose text,
    requested_monthly_payment numeric(18,2),
    application_status character varying(20) DEFAULT 'DRAFT'::character varying NOT NULL,
    missing_data_status character varying(20) DEFAULT 'PARTIAL'::character varying NOT NULL,
    decision_date timestamp with time zone,
    requested_data_deadline timestamp with time zone,
    requested_term_months integer,
    CONSTRAINT credit_applications_application_status_check CHECK (((application_status)::text = ANY ((ARRAY['DRAFT'::character varying, 'SUBMITTED'::character varying, 'UNDER_REVIEW'::character varying, 'AWAITING_DATA'::character varying, 'APPROVED'::character varying, 'REJECTED'::character varying, 'CANCELLED'::character varying])::text[]))),
    CONSTRAINT credit_applications_missing_data_status_check CHECK (((missing_data_status)::text = ANY ((ARRAY['COMPLETE'::character varying, 'PARTIAL'::character varying, 'CRITICAL_MISSING'::character varying])::text[]))),
    CONSTRAINT credit_applications_requested_amount_check CHECK (((requested_amount IS NULL) OR (requested_amount > (0)::numeric))),
    CONSTRAINT credit_applications_requested_monthly_payment_check CHECK (((requested_monthly_payment IS NULL) OR (requested_monthly_payment >= (0)::numeric))),
    CONSTRAINT credit_applications_requested_term_days_check CHECK (((requested_term_days IS NULL) OR (requested_term_days > 0)))
);


--
-- TOC entry 234 (class 1259 OID 19222)
-- Name: credit_applications_application_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_applications ALTER COLUMN application_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_applications_application_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 247 (class 1259 OID 19366)
-- Name: credit_decisions; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_decisions (
    decision_id bigint NOT NULL,
    application_id bigint NOT NULL,
    scoring_result_id bigint,
    policy_version character varying(50) NOT NULL,
    decided_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    eligibility_status character varying(20) NOT NULL,
    decision character varying(20) NOT NULL,
    approved_amount numeric(18,2),
    approved_term_days integer,
    reasons jsonb,
    CONSTRAINT credit_decisions_approved_amount_check CHECK (((approved_amount IS NULL) OR (approved_amount >= (0)::numeric))),
    CONSTRAINT credit_decisions_approved_term_days_check CHECK (((approved_term_days IS NULL) OR (approved_term_days >= 0))),
    CONSTRAINT credit_decisions_decision_check CHECK (((decision)::text = ANY ((ARRAY['APPROVE'::character varying, 'REJECT'::character varying, 'REQUEST_DATA'::character varying, 'MANUAL_REVIEW'::character varying])::text[]))),
    CONSTRAINT credit_decisions_eligibility_status_check CHECK (((eligibility_status)::text = ANY ((ARRAY['ELIGIBLE'::character varying, 'INELIGIBLE'::character varying, 'NEEDS_DATA'::character varying])::text[])))
);


--
-- TOC entry 246 (class 1259 OID 19365)
-- Name: credit_decisions_decision_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_decisions ALTER COLUMN decision_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_decisions_decision_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 230 (class 1259 OID 19170)
-- Name: credit_history_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_history_events (
    event_id bigint NOT NULL,
    company_id bigint NOT NULL,
    obligation_id bigint,
    event_type character varying(20) NOT NULL,
    event_date date NOT NULL,
    overdue_days integer,
    overdue_amount numeric(18,2),
    resolution_date date,
    event_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    source_event_id text,
    source_checked_at timestamp with time zone,
    CONSTRAINT credit_history_events_check CHECK (((resolution_date IS NULL) OR (resolution_date >= event_date))),
    CONSTRAINT credit_history_events_event_status_check CHECK (((event_status)::text = ANY ((ARRAY['OPEN'::character varying, 'RESOLVED'::character varying, 'IN_PROGRESS'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT credit_history_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['DELINQUENCY'::character varying, 'RESTRUCTURING'::character varying, 'DEFAULT'::character varying, 'WRITE_OFF'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT credit_history_events_overdue_amount_check CHECK (((overdue_amount IS NULL) OR (overdue_amount >= (0)::numeric))),
    CONSTRAINT credit_history_events_overdue_days_check CHECK (((overdue_days IS NULL) OR (overdue_days >= 0)))
);


--
-- TOC entry 229 (class 1259 OID 19169)
-- Name: credit_history_events_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_history_events ALTER COLUMN event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_history_events_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 241 (class 1259 OID 19296)
-- Name: credit_line_operations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_line_operations (
    operation_id bigint NOT NULL,
    company_id bigint NOT NULL,
    application_id bigint NOT NULL,
    product_code character varying(10) NOT NULL,
    operation_date timestamp with time zone NOT NULL,
    operation_type character varying(20) NOT NULL,
    operation_amount numeric(18,2) NOT NULL,
    credit_limit numeric(18,2),
    outstanding_debt numeric(18,2),
    available_limit numeric(18,2),
    source_operation_id text,
    CONSTRAINT credit_line_operations_available_limit_check CHECK (((available_limit IS NULL) OR (available_limit >= (0)::numeric))),
    CONSTRAINT credit_line_operations_credit_limit_check CHECK (((credit_limit IS NULL) OR (credit_limit >= (0)::numeric))),
    CONSTRAINT credit_line_operations_operation_amount_check CHECK ((operation_amount >= (0)::numeric)),
    CONSTRAINT credit_line_operations_operation_type_check CHECK (((operation_type)::text = ANY ((ARRAY['DRAWDOWN'::character varying, 'REPAYMENT'::character varying, 'LIMIT_CHANGE'::character varying, 'INTEREST'::character varying])::text[]))),
    CONSTRAINT credit_line_operations_outstanding_debt_check CHECK (((outstanding_debt IS NULL) OR (outstanding_debt >= (0)::numeric)))
);


--
-- TOC entry 240 (class 1259 OID 19295)
-- Name: credit_line_operations_operation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_line_operations ALTER COLUMN operation_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_line_operations_operation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 226 (class 1259 OID 19125)
-- Name: credit_obligations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_obligations (
    obligation_id bigint NOT NULL,
    company_id bigint NOT NULL,
    creditor_name text,
    obligation_type character varying(20) NOT NULL,
    contract_ref character varying(100),
    contract_date date,
    maturity_date date,
    disbursement_date date,
    actual_close_date date,
    first_default_date date,
    original_amount numeric(18,2),
    outstanding_balance numeric(18,2),
    monthly_payment numeric(18,2),
    interest_rate numeric(8,4),
    overdue_amount numeric(18,2),
    obligation_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    CONSTRAINT credit_obligations_check CHECK (((maturity_date IS NULL) OR (contract_date IS NULL) OR (maturity_date >= contract_date))),
    CONSTRAINT credit_obligations_interest_rate_check CHECK (((interest_rate IS NULL) OR (interest_rate >= (0)::numeric))),
    CONSTRAINT credit_obligations_monthly_payment_check CHECK (((monthly_payment IS NULL) OR (monthly_payment >= (0)::numeric))),
    CONSTRAINT credit_obligations_obligation_status_check CHECK (((obligation_status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'OVERDUE'::character varying, 'RESTRUCTURED'::character varying, 'CLOSED'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT credit_obligations_obligation_type_check CHECK (((obligation_type)::text = ANY ((ARRAY['LOAN'::character varying, 'CREDIT_LINE'::character varying, 'OVERDRAFT'::character varying, 'LEASING'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT credit_obligations_original_amount_check CHECK (((original_amount IS NULL) OR (original_amount >= (0)::numeric))),
    CONSTRAINT credit_obligations_outstanding_balance_check CHECK (((outstanding_balance IS NULL) OR (outstanding_balance >= (0)::numeric))),
    CONSTRAINT credit_obligations_overdue_amount_check CHECK (((overdue_amount IS NULL) OR (overdue_amount >= (0)::numeric)))
);


--
-- TOC entry 225 (class 1259 OID 19124)
-- Name: credit_obligations_obligation_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_obligations ALTER COLUMN obligation_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_obligations_obligation_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 265 (class 1259 OID 19579)
-- Name: credit_product_eligibility_rules; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_product_eligibility_rules (
    rule_id bigint NOT NULL,
    terms_id bigint NOT NULL,
    rule_code text NOT NULL,
    rule_description text NOT NULL,
    parameter_name text,
    comparison_operator character varying(10),
    threshold_value jsonb,
    required_data_field text,
    severity character varying(20) DEFAULT 'REVIEW'::character varying NOT NULL,
    CONSTRAINT credit_product_eligibility_rules_comparison_operator_check CHECK (((comparison_operator IS NULL) OR ((comparison_operator)::text = ANY ((ARRAY['EQ'::character varying, 'NE'::character varying, 'GT'::character varying, 'GTE'::character varying, 'LT'::character varying, 'LTE'::character varying, 'IN'::character varying])::text[])))),
    CONSTRAINT credit_product_eligibility_rules_severity_check CHECK (((severity)::text = ANY ((ARRAY['BLOCK'::character varying, 'REVIEW'::character varying, 'INFORMATION'::character varying])::text[])))
);


--
-- TOC entry 264 (class 1259 OID 19578)
-- Name: credit_product_eligibility_rules_rule_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_product_eligibility_rules ALTER COLUMN rule_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_product_eligibility_rules_rule_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 267 (class 1259 OID 19597)
-- Name: credit_product_fees; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_product_fees (
    fee_id bigint NOT NULL,
    terms_id bigint NOT NULL,
    fee_name text NOT NULL,
    fee_type character varying(30) NOT NULL,
    fee_value numeric(18,4),
    fee_frequency text,
    applies_when text,
    CONSTRAINT credit_product_fees_fee_type_check CHECK (((fee_type)::text = ANY ((ARRAY['FIXED'::character varying, 'PERCENT_OF_LIMIT'::character varying, 'PERCENT_OF_AMOUNT'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- TOC entry 266 (class 1259 OID 19596)
-- Name: credit_product_fees_fee_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_product_fees ALTER COLUMN fee_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_product_fees_fee_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 263 (class 1259 OID 19565)
-- Name: credit_product_purposes; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_product_purposes (
    purpose_id bigint NOT NULL,
    terms_id bigint NOT NULL,
    purpose_name text NOT NULL,
    is_allowed boolean DEFAULT true NOT NULL,
    restriction_description text
);


--
-- TOC entry 262 (class 1259 OID 19564)
-- Name: credit_product_purposes_purpose_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_product_purposes ALTER COLUMN purpose_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_product_purposes_purpose_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 259 (class 1259 OID 19529)
-- Name: credit_product_rate_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_product_rate_options (
    rate_option_id bigint NOT NULL,
    terms_id bigint NOT NULL,
    option_name text NOT NULL,
    min_annual_rate_pct numeric(9,4),
    max_annual_rate_pct numeric(9,4),
    additional_service_name text,
    service_fee_type character varying(30),
    service_fee_frequency character varying(20),
    service_fee_amount numeric(18,4),
    discount_end_condition text,
    max_tranche_term_days integer,
    limit_review_frequency character varying(30),
    limit_reduction_protected boolean,
    service_fee_allowed_pct numeric(6,2)[],
    max_tranche_term_months integer,
    CONSTRAINT credit_product_rate_options_check CHECK (((max_annual_rate_pct IS NULL) OR (min_annual_rate_pct IS NULL) OR (max_annual_rate_pct >= min_annual_rate_pct))),
    CONSTRAINT credit_product_rate_options_max_annual_rate_pct_check CHECK (((max_annual_rate_pct IS NULL) OR (max_annual_rate_pct >= (0)::numeric))),
    CONSTRAINT credit_product_rate_options_min_annual_rate_pct_check CHECK (((min_annual_rate_pct IS NULL) OR (min_annual_rate_pct >= (0)::numeric))),
    CONSTRAINT credit_product_rate_options_service_fee_amount_check CHECK (((service_fee_amount IS NULL) OR (service_fee_amount >= (0)::numeric))),
    CONSTRAINT credit_product_rate_options_service_fee_type_check CHECK (((service_fee_type IS NULL) OR ((service_fee_type)::text = ANY ((ARRAY['FIXED'::character varying, 'PERCENT_OF_LIMIT'::character varying, 'PERCENT_OF_AMOUNT'::character varying, 'OTHER'::character varying])::text[]))))
);


--
-- TOC entry 258 (class 1259 OID 19528)
-- Name: credit_product_rate_options_rate_option_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_product_rate_options ALTER COLUMN rate_option_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_product_rate_options_rate_option_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 261 (class 1259 OID 19549)
-- Name: credit_product_repayment_options; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_product_repayment_options (
    repayment_option_id bigint NOT NULL,
    terms_id bigint NOT NULL,
    repayment_type character varying(30) NOT NULL,
    principal_payment_frequency character varying(20),
    interest_payment_frequency character varying(20),
    automatic_from_account boolean,
    description text,
    CONSTRAINT credit_product_repayment_options_repayment_type_check CHECK (((repayment_type)::text = ANY ((ARRAY['ANNUITY'::character varying, 'EQUAL_PRINCIPAL'::character varying, 'BULLET'::character varying, 'CASH_SWEEP'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- TOC entry 260 (class 1259 OID 19548)
-- Name: credit_product_repayment_options_repayment_option_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_product_repayment_options ALTER COLUMN repayment_option_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_product_repayment_options_repayment_option_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 257 (class 1259 OID 19492)
-- Name: credit_product_terms; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_product_terms (
    terms_id bigint NOT NULL,
    product_code character varying(10) NOT NULL,
    version_code text NOT NULL,
    effective_from date,
    effective_to date,
    min_amount numeric(18,2),
    max_amount numeric(18,2),
    min_contract_term_value integer,
    max_contract_term_value integer,
    contract_term_unit character varying(10),
    min_tranche_amount numeric(18,2),
    min_tranche_term_value integer,
    max_tranche_term_value integer,
    tranche_term_unit character varying(10),
    drawdown_period_months integer,
    drawdown_end_before_maturity_months integer,
    is_revolving boolean,
    auto_renewal boolean,
    renewal_period_months integer,
    requires_collateral boolean,
    guarantor_requirement character varying(20),
    min_business_age_months integer,
    allowed_entity_types text[],
    allowed_sme_categories text[],
    source_url text,
    source_checked_at timestamp with time zone,
    CONSTRAINT credit_product_terms_check CHECK (((max_amount IS NULL) OR (min_amount IS NULL) OR (max_amount >= min_amount))),
    CONSTRAINT credit_product_terms_check1 CHECK (((effective_to IS NULL) OR (effective_from IS NULL) OR (effective_to >= effective_from))),
    CONSTRAINT credit_product_terms_check2 CHECK (((max_contract_term_value IS NULL) OR (min_contract_term_value IS NULL) OR (max_contract_term_value >= min_contract_term_value))),
    CONSTRAINT credit_product_terms_check3 CHECK (((max_tranche_term_value IS NULL) OR (min_tranche_term_value IS NULL) OR (max_tranche_term_value >= min_tranche_term_value))),
    CONSTRAINT credit_product_terms_check4 CHECK ((((min_contract_term_value IS NULL) AND (max_contract_term_value IS NULL)) OR (contract_term_unit IS NOT NULL))),
    CONSTRAINT credit_product_terms_check5 CHECK ((((min_tranche_term_value IS NULL) AND (max_tranche_term_value IS NULL)) OR (tranche_term_unit IS NOT NULL))),
    CONSTRAINT credit_product_terms_contract_term_unit_check CHECK (((contract_term_unit IS NULL) OR ((contract_term_unit)::text = ANY ((ARRAY['DAYS'::character varying, 'MONTHS'::character varying])::text[])))),
    CONSTRAINT credit_product_terms_drawdown_end_before_maturity_months_check CHECK (((drawdown_end_before_maturity_months IS NULL) OR (drawdown_end_before_maturity_months >= 0))),
    CONSTRAINT credit_product_terms_drawdown_period_months_check CHECK (((drawdown_period_months IS NULL) OR (drawdown_period_months > 0))),
    CONSTRAINT credit_product_terms_guarantor_requirement_check CHECK (((guarantor_requirement IS NULL) OR ((guarantor_requirement)::text = ANY ((ARRAY['REQUIRED'::character varying, 'NOT_REQUIRED'::character varying, 'CONDITIONAL'::character varying, 'UNKNOWN'::character varying])::text[])))),
    CONSTRAINT credit_product_terms_max_amount_check CHECK (((max_amount IS NULL) OR (max_amount >= (0)::numeric))),
    CONSTRAINT credit_product_terms_max_contract_term_value_check CHECK (((max_contract_term_value IS NULL) OR (max_contract_term_value > 0))),
    CONSTRAINT credit_product_terms_max_tranche_term_value_check CHECK (((max_tranche_term_value IS NULL) OR (max_tranche_term_value > 0))),
    CONSTRAINT credit_product_terms_min_amount_check CHECK (((min_amount IS NULL) OR (min_amount >= (0)::numeric))),
    CONSTRAINT credit_product_terms_min_business_age_months_check CHECK (((min_business_age_months IS NULL) OR (min_business_age_months >= 0))),
    CONSTRAINT credit_product_terms_min_contract_term_value_check CHECK (((min_contract_term_value IS NULL) OR (min_contract_term_value > 0))),
    CONSTRAINT credit_product_terms_min_tranche_amount_check CHECK (((min_tranche_amount IS NULL) OR (min_tranche_amount >= (0)::numeric))),
    CONSTRAINT credit_product_terms_min_tranche_term_value_check CHECK (((min_tranche_term_value IS NULL) OR (min_tranche_term_value > 0))),
    CONSTRAINT credit_product_terms_renewal_period_months_check CHECK (((renewal_period_months IS NULL) OR (renewal_period_months > 0))),
    CONSTRAINT credit_product_terms_tranche_term_unit_check CHECK (((tranche_term_unit IS NULL) OR ((tranche_term_unit)::text = ANY ((ARRAY['DAYS'::character varying, 'MONTHS'::character varying])::text[]))))
);


--
-- TOC entry 256 (class 1259 OID 19491)
-- Name: credit_product_terms_terms_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_product_terms ALTER COLUMN terms_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_product_terms_terms_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 233 (class 1259 OID 19213)
-- Name: credit_products; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_products (
    product_code character varying(10) NOT NULL,
    product_name text NOT NULL,
    product_type character varying(20) NOT NULL,
    active boolean DEFAULT true NOT NULL,
    CONSTRAINT credit_products_product_type_check CHECK (((product_type)::text = ANY ((ARRAY['TERM_LOAN'::character varying, 'CREDIT_LINE'::character varying, 'OVERDRAFT'::character varying])::text[])))
);


--
-- TOC entry 228 (class 1259 OID 19147)
-- Name: credit_repayment_history; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.credit_repayment_history (
    repayment_id bigint NOT NULL,
    obligation_id bigint NOT NULL,
    period_date date NOT NULL,
    scheduled_payment numeric(18,2),
    actual_payment numeric(18,2),
    outstanding_balance numeric(18,2),
    overdue_amount numeric(18,2),
    overdue_days integer,
    default_flag boolean,
    observation_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    source_record_id text,
    source_checked_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT credit_repayment_history_actual_payment_check CHECK (((actual_payment IS NULL) OR (actual_payment >= (0)::numeric))),
    CONSTRAINT credit_repayment_history_observation_status_check CHECK (((observation_status)::text = ANY ((ARRAY['ACTIVE'::character varying, 'CLOSED'::character varying, 'DEFAULT'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT credit_repayment_history_outstanding_balance_check CHECK (((outstanding_balance IS NULL) OR (outstanding_balance >= (0)::numeric))),
    CONSTRAINT credit_repayment_history_overdue_amount_check CHECK (((overdue_amount IS NULL) OR (overdue_amount >= (0)::numeric))),
    CONSTRAINT credit_repayment_history_overdue_days_check CHECK (((overdue_days IS NULL) OR (overdue_days >= 0))),
    CONSTRAINT credit_repayment_history_scheduled_payment_check CHECK (((scheduled_payment IS NULL) OR (scheduled_payment >= (0)::numeric)))
);


--
-- TOC entry 227 (class 1259 OID 19146)
-- Name: credit_repayment_history_repayment_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.credit_repayment_history ALTER COLUMN repayment_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.credit_repayment_history_repayment_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 243 (class 1259 OID 19324)
-- Name: data_quality_checks; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.data_quality_checks (
    check_id bigint NOT NULL,
    company_id bigint NOT NULL,
    application_id bigint,
    source_name character varying(50),
    field_name character varying(100),
    check_type character varying(20) NOT NULL,
    check_status character varying(20) NOT NULL,
    checked_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    data_as_of timestamp with time zone,
    missing_fields jsonb,
    conflict_description text,
    severity character varying(20) DEFAULT 'MEDIUM'::character varying NOT NULL,
    resolution_status character varying(20) DEFAULT 'OPEN'::character varying NOT NULL,
    resolution_comment text,
    CONSTRAINT data_quality_checks_check_status_check CHECK (((check_status)::text = ANY ((ARRAY['PASS'::character varying, 'FAIL'::character varying, 'WARNING'::character varying, 'NOT_CHECKED'::character varying])::text[]))),
    CONSTRAINT data_quality_checks_check_type_check CHECK (((check_type)::text = ANY ((ARRAY['COMPLETENESS'::character varying, 'FORMAT'::character varying, 'CONSISTENCY'::character varying, 'FRESHNESS'::character varying, 'IDENTITY_MATCH'::character varying])::text[]))),
    CONSTRAINT data_quality_checks_resolution_status_check CHECK (((resolution_status)::text = ANY ((ARRAY['OPEN'::character varying, 'RESOLVED'::character varying, 'ACCEPTED'::character varying])::text[]))),
    CONSTRAINT data_quality_checks_severity_check CHECK (((severity)::text = ANY ((ARRAY['LOW'::character varying, 'MEDIUM'::character varying, 'HIGH'::character varying, 'CRITICAL'::character varying])::text[])))
);


--
-- TOC entry 242 (class 1259 OID 19323)
-- Name: data_quality_checks_check_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.data_quality_checks ALTER COLUMN check_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.data_quality_checks_check_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 224 (class 1259 OID 19108)
-- Name: financial_statements; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.financial_statements (
    statement_id bigint NOT NULL,
    company_id bigint NOT NULL,
    period_start date NOT NULL,
    period_end date NOT NULL,
    statement_type character varying(20) NOT NULL,
    revenue numeric(18,2),
    cost_of_sales numeric(18,2),
    gross_profit numeric(18,2),
    operating_expenses numeric(18,2),
    operating_profit numeric(18,2),
    net_profit numeric(18,2),
    total_assets numeric(18,2),
    current_assets numeric(18,2),
    cash_and_equivalents numeric(18,2),
    short_term_liabilities numeric(18,2),
    total_liabilities numeric(18,2),
    equity numeric(18,2),
    source_document_id text,
    source_checked_at timestamp with time zone,
    is_verified boolean,
    CONSTRAINT financial_statements_check CHECK ((period_end >= period_start)),
    CONSTRAINT financial_statements_statement_type_check CHECK (((statement_type)::text = ANY ((ARRAY['ANNUAL'::character varying, 'INTERIM'::character varying, 'MANAGEMENT'::character varying, 'OTHER'::character varying])::text[])))
);


--
-- TOC entry 223 (class 1259 OID 19107)
-- Name: financial_statements_statement_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.financial_statements ALTER COLUMN statement_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.financial_statements_statement_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 239 (class 1259 OID 19277)
-- Name: guarantors; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.guarantors (
    guarantor_id bigint NOT NULL,
    application_id bigint NOT NULL,
    guarantor_type character varying(20) NOT NULL,
    name text NOT NULL,
    inn character varying(12),
    ogrn character varying(13),
    ogrnip character varying(15),
    relationship_type character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    existing_obligations_amount numeric(18,2),
    financial_capacity_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    source_checked_at timestamp with time zone,
    CONSTRAINT guarantors_existing_obligations_amount_check CHECK (((existing_obligations_amount IS NULL) OR (existing_obligations_amount >= (0)::numeric))),
    CONSTRAINT guarantors_financial_capacity_status_check CHECK (((financial_capacity_status)::text = ANY ((ARRAY['SUFFICIENT'::character varying, 'INSUFFICIENT'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT guarantors_guarantor_type_check CHECK (((guarantor_type)::text = ANY ((ARRAY['INDIVIDUAL'::character varying, 'INDIVIDUAL_ENTREPRENEUR'::character varying, 'LEGAL_ENTITY'::character varying])::text[]))),
    CONSTRAINT guarantors_relationship_type_check CHECK (((relationship_type)::text = ANY ((ARRAY['OWNER'::character varying, 'DIRECTOR'::character varying, 'RELATED_PARTY'::character varying, 'OTHER'::character varying, 'UNKNOWN'::character varying])::text[])))
);


--
-- TOC entry 238 (class 1259 OID 19276)
-- Name: guarantors_guarantor_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.guarantors ALTER COLUMN guarantor_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.guarantors_guarantor_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 232 (class 1259 OID 19194)
-- Name: legal_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.legal_events (
    legal_event_id bigint NOT NULL,
    company_id bigint NOT NULL,
    source_name character varying(20) NOT NULL,
    source_record_id text,
    event_type character varying(30) NOT NULL,
    event_date date,
    case_number character varying(100),
    counterparty_name text,
    amount numeric(18,2),
    event_status character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    company_role character varying(20) DEFAULT 'UNKNOWN'::character varying NOT NULL,
    description text,
    source_checked_at timestamp with time zone,
    CONSTRAINT legal_events_amount_check CHECK (((amount IS NULL) OR (amount >= (0)::numeric))),
    CONSTRAINT legal_events_company_role_check CHECK (((company_role)::text = ANY ((ARRAY['PLAINTIFF'::character varying, 'DEFENDANT'::character varying, 'DEBTOR'::character varying, 'CREDITOR'::character varying, 'OTHER'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT legal_events_event_status_check CHECK (((event_status)::text = ANY ((ARRAY['OPEN'::character varying, 'IN_PROGRESS'::character varying, 'CLOSED'::character varying, 'TERMINATED'::character varying, 'UNKNOWN'::character varying])::text[]))),
    CONSTRAINT legal_events_event_type_check CHECK (((event_type)::text = ANY ((ARRAY['COURT_CASE'::character varying, 'ENFORCEMENT_PROCEEDING'::character varying, 'TAX_DEBT'::character varying, 'BANKRUPTCY'::character varying, 'OTHER'::character varying])::text[]))),
    CONSTRAINT legal_events_source_name_check CHECK (((source_name)::text = ANY ((ARRAY['KAD'::character varying, 'FNS'::character varying, 'FEDRESURS'::character varying, 'FSSP'::character varying])::text[])))
);


--
-- TOC entry 231 (class 1259 OID 19193)
-- Name: legal_events_legal_event_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.legal_events ALTER COLUMN legal_event_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.legal_events_legal_event_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 279 (class 1259 OID 24577)
-- Name: macro_indicators; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.macro_indicators (
    indicator_id bigint NOT NULL,
    indicator_code character varying(50) NOT NULL,
    indicator_value numeric(12,4) NOT NULL,
    effective_date date NOT NULL,
    source character varying(100) NOT NULL,
    loaded_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT macro_indicators_code_not_blank CHECK ((btrim((indicator_code)::text) <> ''::text)),
    CONSTRAINT macro_indicators_key_rate_range CHECK ((((indicator_code)::text <> 'KEY_RATE'::text) OR (indicator_value <= (100)::numeric))),
    CONSTRAINT macro_indicators_source_not_blank CHECK ((btrim((source)::text) <> ''::text)),
    CONSTRAINT macro_indicators_value_nonnegative CHECK ((indicator_value >= (0)::numeric))
);


--
-- TOC entry 278 (class 1259 OID 24576)
-- Name: macro_indicators_indicator_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.macro_indicators ALTER COLUMN indicator_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.macro_indicators_indicator_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 281 (class 1259 OID 24591)
-- Name: risk_policy_parameters; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.risk_policy_parameters (
    policy_id bigint NOT NULL,
    product_code character varying(3) NOT NULL,
    policy_version character varying(50) NOT NULL,
    funding_spread_pct numeric(8,4) NOT NULL,
    operating_cost_pct numeric(8,4) NOT NULL,
    required_margin_pct numeric(8,4) NOT NULL,
    lgd_pct numeric(8,4) NOT NULL,
    effective_from date NOT NULL,
    effective_to date,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT risk_policy_parameters_dates CHECK (((effective_to IS NULL) OR (effective_to >= effective_from))),
    CONSTRAINT risk_policy_parameters_lgd_range CHECK (((lgd_pct >= (0)::numeric) AND (lgd_pct <= (100)::numeric))),
    CONSTRAINT risk_policy_parameters_margin_range CHECK (((required_margin_pct >= (0)::numeric) AND (required_margin_pct <= (100)::numeric))),
    CONSTRAINT risk_policy_parameters_operating_range CHECK (((operating_cost_pct >= (0)::numeric) AND (operating_cost_pct <= (100)::numeric))),
    CONSTRAINT risk_policy_parameters_spread_range CHECK (((funding_spread_pct >= ('-100'::integer)::numeric) AND (funding_spread_pct <= (100)::numeric))),
    CONSTRAINT risk_policy_parameters_version_not_blank CHECK ((btrim((policy_version)::text) <> ''::text))
);


--
-- TOC entry 280 (class 1259 OID 24590)
-- Name: risk_policy_parameters_policy_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.risk_policy_parameters ALTER COLUMN policy_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.risk_policy_parameters_policy_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 245 (class 1259 OID 19349)
-- Name: scoring_results; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.scoring_results (
    scoring_result_id bigint NOT NULL,
    application_id bigint NOT NULL,
    model_version character varying(50) NOT NULL,
    scored_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    score numeric(12,4),
    pd numeric(8,6),
    risk_grade character varying(20) DEFAULT 'UNRATED'::character varying NOT NULL,
    feature_snapshot jsonb,
    source_snapshot_date timestamp with time zone,
    CONSTRAINT scoring_results_pd_check CHECK (((pd IS NULL) OR ((pd >= (0)::numeric) AND (pd <= (1)::numeric)))),
    CONSTRAINT scoring_results_risk_grade_check CHECK (((risk_grade)::text = ANY ((ARRAY['LOW'::character varying, 'MEDIUM'::character varying, 'HIGH'::character varying, 'VERY_HIGH'::character varying, 'UNRATED'::character varying])::text[])))
);


--
-- TOC entry 244 (class 1259 OID 19348)
-- Name: scoring_results_scoring_result_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.scoring_results ALTER COLUMN scoring_result_id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.scoring_results_scoring_result_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- TOC entry 5197 (class 2606 OID 19638)
-- Name: application_data_requests application_data_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_data_requests
    ADD CONSTRAINT application_data_requests_pkey PRIMARY KEY (request_id);


--
-- TOC entry 5146 (class 2606 OID 19404)
-- Name: application_details application_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_details
    ADD CONSTRAINT application_details_pkey PRIMARY KEY (application_id);


--
-- TOC entry 5210 (class 2606 OID 19714)
-- Name: application_field_history application_field_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_history
    ADD CONSTRAINT application_field_history_pkey PRIMARY KEY (history_id);


--
-- TOC entry 5148 (class 2606 OID 19416)
-- Name: application_field_requirements application_field_requirements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_requirements
    ADD CONSTRAINT application_field_requirements_pkey PRIMARY KEY (product_code, field_number);


--
-- TOC entry 5150 (class 2606 OID 19418)
-- Name: application_field_requirements application_field_requirements_product_code_field_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_requirements
    ADD CONSTRAINT application_field_requirements_product_code_field_code_key UNIQUE (product_code, field_code);


--
-- TOC entry 5154 (class 2606 OID 19435)
-- Name: application_field_values application_field_values_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_values
    ADD CONSTRAINT application_field_values_pkey PRIMARY KEY (application_id, field_code);


--
-- TOC entry 5167 (class 2606 OID 19485)
-- Name: application_product_details application_product_details_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_details
    ADD CONSTRAINT application_product_details_pkey PRIMARY KEY (application_id);


--
-- TOC entry 5201 (class 2606 OID 19661)
-- Name: application_product_terms application_product_terms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT application_product_terms_pkey PRIMARY KEY (offer_id);


--
-- TOC entry 5205 (class 2606 OID 19696)
-- Name: application_snapshots application_snapshots_application_id_snapshot_version_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_snapshots
    ADD CONSTRAINT application_snapshots_application_id_snapshot_version_key UNIQUE (application_id, snapshot_version);


--
-- TOC entry 5207 (class 2606 OID 19694)
-- Name: application_snapshots application_snapshots_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_snapshots
    ADD CONSTRAINT application_snapshots_pkey PRIMARY KEY (snapshot_id);


--
-- TOC entry 5092 (class 2606 OID 19101)
-- Name: bank_transactions bank_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_transactions
    ADD CONSTRAINT bank_transactions_pkey PRIMARY KEY (transaction_id);


--
-- TOC entry 5128 (class 2606 OID 19265)
-- Name: collateral collateral_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collateral
    ADD CONSTRAINT collateral_pkey PRIMARY KEY (collateral_id);


--
-- TOC entry 5088 (class 2606 OID 19088)
-- Name: companies companies_inn_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_inn_key UNIQUE (inn);


--
-- TOC entry 5090 (class 2606 OID 19086)
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (company_id);


--
-- TOC entry 5157 (class 2606 OID 19454)
-- Name: company_bank_accounts company_bank_accounts_company_id_account_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_bank_accounts
    ADD CONSTRAINT company_bank_accounts_company_id_account_number_key UNIQUE (company_id, account_number);


--
-- TOC entry 5159 (class 2606 OID 19452)
-- Name: company_bank_accounts company_bank_accounts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_bank_accounts
    ADD CONSTRAINT company_bank_accounts_pkey PRIMARY KEY (account_id);


--
-- TOC entry 5164 (class 2606 OID 19467)
-- Name: company_contacts company_contacts_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_contacts
    ADD CONSTRAINT company_contacts_pkey PRIMARY KEY (contact_id);


--
-- TOC entry 5194 (class 2606 OID 19622)
-- Name: company_data_provenance company_data_provenance_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_data_provenance
    ADD CONSTRAINT company_data_provenance_pkey PRIMARY KEY (provenance_id);


--
-- TOC entry 5119 (class 2606 OID 19237)
-- Name: credit_applications credit_applications_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_applications
    ADD CONSTRAINT credit_applications_pkey PRIMARY KEY (application_id);


--
-- TOC entry 5142 (class 2606 OID 19377)
-- Name: credit_decisions credit_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_decisions
    ADD CONSTRAINT credit_decisions_pkey PRIMARY KEY (decision_id);


--
-- TOC entry 5111 (class 2606 OID 19182)
-- Name: credit_history_events credit_history_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_history_events
    ADD CONSTRAINT credit_history_events_pkey PRIMARY KEY (event_id);


--
-- TOC entry 5132 (class 2606 OID 19307)
-- Name: credit_line_operations credit_line_operations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_line_operations
    ADD CONSTRAINT credit_line_operations_pkey PRIMARY KEY (operation_id);


--
-- TOC entry 5100 (class 2606 OID 19140)
-- Name: credit_obligations credit_obligations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_obligations
    ADD CONSTRAINT credit_obligations_pkey PRIMARY KEY (obligation_id);


--
-- TOC entry 5188 (class 2606 OID 19588)
-- Name: credit_product_eligibility_rules credit_product_eligibility_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_eligibility_rules
    ADD CONSTRAINT credit_product_eligibility_rules_pkey PRIMARY KEY (rule_id);


--
-- TOC entry 5190 (class 2606 OID 19590)
-- Name: credit_product_eligibility_rules credit_product_eligibility_rules_terms_id_rule_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_eligibility_rules
    ADD CONSTRAINT credit_product_eligibility_rules_terms_id_rule_code_key UNIQUE (terms_id, rule_code);


--
-- TOC entry 5192 (class 2606 OID 19604)
-- Name: credit_product_fees credit_product_fees_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_fees
    ADD CONSTRAINT credit_product_fees_pkey PRIMARY KEY (fee_id);


--
-- TOC entry 5186 (class 2606 OID 19572)
-- Name: credit_product_purposes credit_product_purposes_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_purposes
    ADD CONSTRAINT credit_product_purposes_pkey PRIMARY KEY (purpose_id);


--
-- TOC entry 5176 (class 2606 OID 19540)
-- Name: credit_product_rate_options credit_product_rate_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_rate_options
    ADD CONSTRAINT credit_product_rate_options_pkey PRIMARY KEY (rate_option_id);


--
-- TOC entry 5178 (class 2606 OID 19542)
-- Name: credit_product_rate_options credit_product_rate_options_rate_option_id_terms_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_rate_options
    ADD CONSTRAINT credit_product_rate_options_rate_option_id_terms_id_key UNIQUE (rate_option_id, terms_id);


--
-- TOC entry 5181 (class 2606 OID 19558)
-- Name: credit_product_repayment_options credit_product_repayment_optio_repayment_option_id_terms_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_repayment_options
    ADD CONSTRAINT credit_product_repayment_optio_repayment_option_id_terms_id_key UNIQUE (repayment_option_id, terms_id);


--
-- TOC entry 5183 (class 2606 OID 19556)
-- Name: credit_product_repayment_options credit_product_repayment_options_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_repayment_options
    ADD CONSTRAINT credit_product_repayment_options_pkey PRIMARY KEY (repayment_option_id);


--
-- TOC entry 5169 (class 2606 OID 19518)
-- Name: credit_product_terms credit_product_terms_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_terms
    ADD CONSTRAINT credit_product_terms_pkey PRIMARY KEY (terms_id);


--
-- TOC entry 5171 (class 2606 OID 19520)
-- Name: credit_product_terms credit_product_terms_product_code_version_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_terms
    ADD CONSTRAINT credit_product_terms_product_code_version_code_key UNIQUE (product_code, version_code);


--
-- TOC entry 5173 (class 2606 OID 19522)
-- Name: credit_product_terms credit_product_terms_terms_id_product_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_terms
    ADD CONSTRAINT credit_product_terms_terms_id_product_code_key UNIQUE (terms_id, product_code);


--
-- TOC entry 5117 (class 2606 OID 19221)
-- Name: credit_products credit_products_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_products
    ADD CONSTRAINT credit_products_pkey PRIMARY KEY (product_code);


--
-- TOC entry 5105 (class 2606 OID 19163)
-- Name: credit_repayment_history credit_repayment_history_obligation_id_period_date_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_repayment_history
    ADD CONSTRAINT credit_repayment_history_obligation_id_period_date_key UNIQUE (obligation_id, period_date);


--
-- TOC entry 5107 (class 2606 OID 19161)
-- Name: credit_repayment_history credit_repayment_history_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_repayment_history
    ADD CONSTRAINT credit_repayment_history_pkey PRIMARY KEY (repayment_id);


--
-- TOC entry 5135 (class 2606 OID 19337)
-- Name: data_quality_checks data_quality_checks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_checks
    ADD CONSTRAINT data_quality_checks_pkey PRIMARY KEY (check_id);


--
-- TOC entry 5095 (class 2606 OID 19118)
-- Name: financial_statements financial_statements_company_id_period_start_period_end_sta_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_statements
    ADD CONSTRAINT financial_statements_company_id_period_start_period_end_sta_key UNIQUE (company_id, period_start, period_end, statement_type);


--
-- TOC entry 5097 (class 2606 OID 19116)
-- Name: financial_statements financial_statements_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_statements
    ADD CONSTRAINT financial_statements_pkey PRIMARY KEY (statement_id);


--
-- TOC entry 5130 (class 2606 OID 19289)
-- Name: guarantors guarantors_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guarantors
    ADD CONSTRAINT guarantors_pkey PRIMARY KEY (guarantor_id);


--
-- TOC entry 5115 (class 2606 OID 19207)
-- Name: legal_events legal_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_events
    ADD CONSTRAINT legal_events_pkey PRIMARY KEY (legal_event_id);


--
-- TOC entry 5214 (class 2606 OID 24586)
-- Name: macro_indicators macro_indicators_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.macro_indicators
    ADD CONSTRAINT macro_indicators_pkey PRIMARY KEY (indicator_id);


--
-- TOC entry 5216 (class 2606 OID 24588)
-- Name: macro_indicators macro_indicators_unique_observation; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.macro_indicators
    ADD CONSTRAINT macro_indicators_unique_observation UNIQUE (indicator_code, effective_date, source);


--
-- TOC entry 5219 (class 2606 OID 24602)
-- Name: risk_policy_parameters risk_policy_parameters_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policy_parameters
    ADD CONSTRAINT risk_policy_parameters_pkey PRIMARY KEY (policy_id);


--
-- TOC entry 5221 (class 2606 OID 24604)
-- Name: risk_policy_parameters risk_policy_parameters_product_version_uk; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policy_parameters
    ADD CONSTRAINT risk_policy_parameters_product_version_uk UNIQUE (product_code, policy_version);


--
-- TOC entry 5138 (class 2606 OID 19359)
-- Name: scoring_results scoring_results_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scoring_results
    ADD CONSTRAINT scoring_results_pkey PRIMARY KEY (scoring_result_id);


--
-- TOC entry 5162 (class 2606 OID 19726)
-- Name: company_bank_accounts uq_account_company; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_bank_accounts
    ADD CONSTRAINT uq_account_company UNIQUE (account_id, company_id);


--
-- TOC entry 5122 (class 2606 OID 19716)
-- Name: credit_applications uq_application_company; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_applications
    ADD CONSTRAINT uq_application_company UNIQUE (application_id, company_id);


--
-- TOC entry 5124 (class 2606 OID 19718)
-- Name: credit_applications uq_application_company_product; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_applications
    ADD CONSTRAINT uq_application_company_product UNIQUE (application_id, company_id, product_code);


--
-- TOC entry 5126 (class 2606 OID 19720)
-- Name: credit_applications uq_application_product; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_applications
    ADD CONSTRAINT uq_application_product UNIQUE (application_id, product_code);


--
-- TOC entry 5152 (class 2606 OID 19728)
-- Name: application_field_requirements uq_field_product; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_requirements
    ADD CONSTRAINT uq_field_product UNIQUE (product_code, field_code);


--
-- TOC entry 5103 (class 2606 OID 19722)
-- Name: credit_obligations uq_obligation_company; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_obligations
    ADD CONSTRAINT uq_obligation_company UNIQUE (obligation_id, company_id);


--
-- TOC entry 5140 (class 2606 OID 19724)
-- Name: scoring_results uq_scoring_application; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scoring_results
    ADD CONSTRAINT uq_scoring_application UNIQUE (scoring_result_id, application_id);


--
-- TOC entry 5120 (class 1259 OID 19395)
-- Name: idx_applications_company_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_applications_company_date ON public.credit_applications USING btree (company_id, application_date);


--
-- TOC entry 5160 (class 1259 OID 19819)
-- Name: idx_bank_accounts_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bank_accounts_company ON public.company_bank_accounts USING btree (company_id);


--
-- TOC entry 5093 (class 1259 OID 19388)
-- Name: idx_bank_transactions_company_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_bank_transactions_company_date ON public.bank_transactions USING btree (company_id, transaction_date);


--
-- TOC entry 5165 (class 1259 OID 19820)
-- Name: idx_company_contacts_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_company_contacts_company ON public.company_contacts USING btree (company_id);


--
-- TOC entry 5143 (class 1259 OID 19397)
-- Name: idx_credit_decisions_application_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credit_decisions_application_date ON public.credit_decisions USING btree (application_id, decided_at);


--
-- TOC entry 5112 (class 1259 OID 19393)
-- Name: idx_credit_history_company_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credit_history_company_date ON public.credit_history_events USING btree (company_id, event_date);


--
-- TOC entry 5101 (class 1259 OID 19390)
-- Name: idx_credit_obligations_company; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_credit_obligations_company ON public.credit_obligations USING btree (company_id);


--
-- TOC entry 5198 (class 1259 OID 19822)
-- Name: idx_data_requests_app_status; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_data_requests_app_status ON public.application_data_requests USING btree (application_id, request_status);


--
-- TOC entry 5144 (class 1259 OID 19833)
-- Name: idx_decisions_scoring; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_decisions_scoring ON public.credit_decisions USING btree (scoring_result_id, application_id);


--
-- TOC entry 5211 (class 1259 OID 19825)
-- Name: idx_field_history_application_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_field_history_application_time ON public.application_field_history USING btree (application_id, changed_at DESC);


--
-- TOC entry 5155 (class 1259 OID 19824)
-- Name: idx_field_values_product_field; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_field_values_product_field ON public.application_field_values USING btree (product_code, field_code);


--
-- TOC entry 5098 (class 1259 OID 19389)
-- Name: idx_financial_statements_company_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_financial_statements_company_period ON public.financial_statements USING btree (company_id, period_end);


--
-- TOC entry 5113 (class 1259 OID 19394)
-- Name: idx_legal_events_company_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_legal_events_company_date ON public.legal_events USING btree (company_id, event_date);


--
-- TOC entry 5202 (class 1259 OID 19827)
-- Name: idx_offer_application; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offer_application ON public.application_product_terms USING btree (application_id);


--
-- TOC entry 5203 (class 1259 OID 19828)
-- Name: idx_offer_terms; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_offer_terms ON public.application_product_terms USING btree (terms_id);


--
-- TOC entry 5133 (class 1259 OID 19832)
-- Name: idx_operations_application; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_operations_application ON public.credit_line_operations USING btree (application_id);


--
-- TOC entry 5195 (class 1259 OID 19823)
-- Name: idx_provenance_company_field; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_provenance_company_field ON public.company_data_provenance USING btree (company_id, target_table, target_field);


--
-- TOC entry 5179 (class 1259 OID 19829)
-- Name: idx_rates_terms; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_rates_terms ON public.credit_product_rate_options USING btree (terms_id);


--
-- TOC entry 5108 (class 1259 OID 19392)
-- Name: idx_repayment_history_default; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_repayment_history_default ON public.credit_repayment_history USING btree (obligation_id, period_date) WHERE (default_flag = true);


--
-- TOC entry 5109 (class 1259 OID 19391)
-- Name: idx_repayment_history_period; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_repayment_history_period ON public.credit_repayment_history USING btree (period_date);


--
-- TOC entry 5184 (class 1259 OID 19830)
-- Name: idx_repayment_terms; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_repayment_terms ON public.credit_product_repayment_options USING btree (terms_id);


--
-- TOC entry 5199 (class 1259 OID 19831)
-- Name: idx_requests_defined_field; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_requests_defined_field ON public.application_data_requests USING btree (product_code, field_code);


--
-- TOC entry 5136 (class 1259 OID 19396)
-- Name: idx_scoring_results_application_date; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_scoring_results_application_date ON public.scoring_results USING btree (application_id, scored_at);


--
-- TOC entry 5208 (class 1259 OID 19826)
-- Name: idx_snapshots_application_time; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_snapshots_application_time ON public.application_snapshots USING btree (application_id, created_at DESC);


--
-- TOC entry 5174 (class 1259 OID 19821)
-- Name: idx_terms_product; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX idx_terms_product ON public.credit_product_terms USING btree (product_code);


--
-- TOC entry 5212 (class 1259 OID 24589)
-- Name: macro_indicators_latest_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX macro_indicators_latest_idx ON public.macro_indicators USING btree (indicator_code, effective_date DESC);


--
-- TOC entry 5217 (class 1259 OID 24610)
-- Name: risk_policy_parameters_lookup_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX risk_policy_parameters_lookup_idx ON public.risk_policy_parameters USING btree (product_code, effective_from DESC);


--
-- TOC entry 5281 (class 2620 OID 19817)
-- Name: application_field_history trg_immutable_application_field_history; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_immutable_application_field_history BEFORE DELETE OR UPDATE ON public.application_field_history FOR EACH ROW EXECUTE FUNCTION public.aurelius_reject_history_mutation();


--
-- TOC entry 5280 (class 2620 OID 19818)
-- Name: application_snapshots trg_immutable_application_snapshots; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_immutable_application_snapshots BEFORE DELETE OR UPDATE ON public.application_snapshots FOR EACH ROW EXECUTE FUNCTION public.aurelius_reject_history_mutation();


--
-- TOC entry 5279 (class 2620 OID 19815)
-- Name: application_field_values trg_log_application_field_values; Type: TRIGGER; Schema: public; Owner: -
--

CREATE TRIGGER trg_log_application_field_values AFTER INSERT OR DELETE OR UPDATE ON public.application_field_values FOR EACH ROW EXECUTE FUNCTION public.aurelius_log_field_change();


--
-- TOC entry 5264 (class 2606 OID 19639)
-- Name: application_data_requests application_data_requests_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_data_requests
    ADD CONSTRAINT application_data_requests_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5247 (class 2606 OID 19405)
-- Name: application_details application_details_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_details
    ADD CONSTRAINT application_details_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5248 (class 2606 OID 19419)
-- Name: application_field_requirements application_field_requirements_product_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_requirements
    ADD CONSTRAINT application_field_requirements_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);


--
-- TOC entry 5249 (class 2606 OID 19436)
-- Name: application_field_values application_field_values_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_values
    ADD CONSTRAINT application_field_values_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5254 (class 2606 OID 19486)
-- Name: application_product_details application_product_details_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_details
    ADD CONSTRAINT application_product_details_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5267 (class 2606 OID 19662)
-- Name: application_product_terms application_product_terms_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT application_product_terms_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5268 (class 2606 OID 19672)
-- Name: application_product_terms application_product_terms_rate_option_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT application_product_terms_rate_option_id_fkey FOREIGN KEY (rate_option_id) REFERENCES public.credit_product_rate_options(rate_option_id);


--
-- TOC entry 5269 (class 2606 OID 19677)
-- Name: application_product_terms application_product_terms_repayment_option_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT application_product_terms_repayment_option_id_fkey FOREIGN KEY (repayment_option_id) REFERENCES public.credit_product_repayment_options(repayment_option_id);


--
-- TOC entry 5270 (class 2606 OID 19667)
-- Name: application_product_terms application_product_terms_terms_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT application_product_terms_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);


--
-- TOC entry 5275 (class 2606 OID 19697)
-- Name: application_snapshots application_snapshots_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_snapshots
    ADD CONSTRAINT application_snapshots_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5222 (class 2606 OID 19102)
-- Name: bank_transactions bank_transactions_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.bank_transactions
    ADD CONSTRAINT bank_transactions_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5232 (class 2606 OID 19271)
-- Name: collateral collateral_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collateral
    ADD CONSTRAINT collateral_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5233 (class 2606 OID 19266)
-- Name: collateral collateral_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collateral
    ADD CONSTRAINT collateral_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5252 (class 2606 OID 19455)
-- Name: company_bank_accounts company_bank_accounts_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_bank_accounts
    ADD CONSTRAINT company_bank_accounts_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5253 (class 2606 OID 19468)
-- Name: company_contacts company_contacts_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_contacts
    ADD CONSTRAINT company_contacts_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5263 (class 2606 OID 19623)
-- Name: company_data_provenance company_data_provenance_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.company_data_provenance
    ADD CONSTRAINT company_data_provenance_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5230 (class 2606 OID 19238)
-- Name: credit_applications credit_applications_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_applications
    ADD CONSTRAINT credit_applications_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5231 (class 2606 OID 19243)
-- Name: credit_applications credit_applications_product_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_applications
    ADD CONSTRAINT credit_applications_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);


--
-- TOC entry 5244 (class 2606 OID 19378)
-- Name: credit_decisions credit_decisions_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_decisions
    ADD CONSTRAINT credit_decisions_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5245 (class 2606 OID 19383)
-- Name: credit_decisions credit_decisions_scoring_result_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_decisions
    ADD CONSTRAINT credit_decisions_scoring_result_id_fkey FOREIGN KEY (scoring_result_id) REFERENCES public.scoring_results(scoring_result_id);


--
-- TOC entry 5226 (class 2606 OID 19183)
-- Name: credit_history_events credit_history_events_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_history_events
    ADD CONSTRAINT credit_history_events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5227 (class 2606 OID 19188)
-- Name: credit_history_events credit_history_events_obligation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_history_events
    ADD CONSTRAINT credit_history_events_obligation_id_fkey FOREIGN KEY (obligation_id) REFERENCES public.credit_obligations(obligation_id);


--
-- TOC entry 5236 (class 2606 OID 19313)
-- Name: credit_line_operations credit_line_operations_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_line_operations
    ADD CONSTRAINT credit_line_operations_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5237 (class 2606 OID 19308)
-- Name: credit_line_operations credit_line_operations_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_line_operations
    ADD CONSTRAINT credit_line_operations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5238 (class 2606 OID 19318)
-- Name: credit_line_operations credit_line_operations_product_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_line_operations
    ADD CONSTRAINT credit_line_operations_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);


--
-- TOC entry 5224 (class 2606 OID 19141)
-- Name: credit_obligations credit_obligations_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_obligations
    ADD CONSTRAINT credit_obligations_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5261 (class 2606 OID 19591)
-- Name: credit_product_eligibility_rules credit_product_eligibility_rules_terms_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_eligibility_rules
    ADD CONSTRAINT credit_product_eligibility_rules_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);


--
-- TOC entry 5262 (class 2606 OID 19605)
-- Name: credit_product_fees credit_product_fees_terms_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_fees
    ADD CONSTRAINT credit_product_fees_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);


--
-- TOC entry 5260 (class 2606 OID 19573)
-- Name: credit_product_purposes credit_product_purposes_terms_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_purposes
    ADD CONSTRAINT credit_product_purposes_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);


--
-- TOC entry 5258 (class 2606 OID 19543)
-- Name: credit_product_rate_options credit_product_rate_options_terms_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_rate_options
    ADD CONSTRAINT credit_product_rate_options_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);


--
-- TOC entry 5259 (class 2606 OID 19559)
-- Name: credit_product_repayment_options credit_product_repayment_options_terms_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_repayment_options
    ADD CONSTRAINT credit_product_repayment_options_terms_id_fkey FOREIGN KEY (terms_id) REFERENCES public.credit_product_terms(terms_id);


--
-- TOC entry 5257 (class 2606 OID 19523)
-- Name: credit_product_terms credit_product_terms_product_code_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_product_terms
    ADD CONSTRAINT credit_product_terms_product_code_fkey FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);


--
-- TOC entry 5225 (class 2606 OID 19164)
-- Name: credit_repayment_history credit_repayment_history_obligation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_repayment_history
    ADD CONSTRAINT credit_repayment_history_obligation_id_fkey FOREIGN KEY (obligation_id) REFERENCES public.credit_obligations(obligation_id);


--
-- TOC entry 5240 (class 2606 OID 19343)
-- Name: data_quality_checks data_quality_checks_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_checks
    ADD CONSTRAINT data_quality_checks_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5241 (class 2606 OID 19338)
-- Name: data_quality_checks data_quality_checks_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_checks
    ADD CONSTRAINT data_quality_checks_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5223 (class 2606 OID 19119)
-- Name: financial_statements financial_statements_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.financial_statements
    ADD CONSTRAINT financial_statements_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5234 (class 2606 OID 19739)
-- Name: collateral fk_collateral_same_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.collateral
    ADD CONSTRAINT fk_collateral_same_company FOREIGN KEY (application_id, company_id) REFERENCES public.credit_applications(application_id, company_id);


--
-- TOC entry 5228 (class 2606 OID 19744)
-- Name: credit_history_events fk_credit_event_same_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_history_events
    ADD CONSTRAINT fk_credit_event_same_company FOREIGN KEY (obligation_id, company_id) REFERENCES public.credit_obligations(obligation_id, company_id);


--
-- TOC entry 5246 (class 2606 OID 19729)
-- Name: credit_decisions fk_decision_scoring_same_application; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_decisions
    ADD CONSTRAINT fk_decision_scoring_same_application FOREIGN KEY (scoring_result_id, application_id) REFERENCES public.scoring_results(scoring_result_id, application_id);


--
-- TOC entry 5255 (class 2606 OID 19809)
-- Name: application_product_details fk_details_bank_account_owner; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_details
    ADD CONSTRAINT fk_details_bank_account_owner FOREIGN KEY (overdraft_bank_account_id, company_id) REFERENCES public.company_bank_accounts(account_id, company_id);


--
-- TOC entry 5256 (class 2606 OID 19804)
-- Name: application_product_details fk_details_same_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_details
    ADD CONSTRAINT fk_details_same_company FOREIGN KEY (application_id, company_id) REFERENCES public.credit_applications(application_id, company_id);


--
-- TOC entry 5276 (class 2606 OID 19779)
-- Name: application_field_history fk_history_defined_field; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_history
    ADD CONSTRAINT fk_history_defined_field FOREIGN KEY (product_code, field_code) REFERENCES public.application_field_requirements(product_code, field_code);


--
-- TOC entry 5277 (class 2606 OID 19774)
-- Name: application_field_history fk_history_same_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_history
    ADD CONSTRAINT fk_history_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);


--
-- TOC entry 5239 (class 2606 OID 19734)
-- Name: credit_line_operations fk_line_operation_same_company_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.credit_line_operations
    ADD CONSTRAINT fk_line_operation_same_company_product FOREIGN KEY (application_id, company_id, product_code) REFERENCES public.credit_applications(application_id, company_id, product_code);


--
-- TOC entry 5271 (class 2606 OID 19794)
-- Name: application_product_terms fk_offer_rate_same_terms; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT fk_offer_rate_same_terms FOREIGN KEY (rate_option_id, terms_id) REFERENCES public.credit_product_rate_options(rate_option_id, terms_id);


--
-- TOC entry 5272 (class 2606 OID 19799)
-- Name: application_product_terms fk_offer_repayment_same_terms; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT fk_offer_repayment_same_terms FOREIGN KEY (repayment_option_id, terms_id) REFERENCES public.credit_product_repayment_options(repayment_option_id, terms_id);


--
-- TOC entry 5273 (class 2606 OID 19784)
-- Name: application_product_terms fk_offer_same_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT fk_offer_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);


--
-- TOC entry 5274 (class 2606 OID 19789)
-- Name: application_product_terms fk_offer_terms_same_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_product_terms
    ADD CONSTRAINT fk_offer_terms_same_product FOREIGN KEY (terms_id, product_code) REFERENCES public.credit_product_terms(terms_id, product_code);


--
-- TOC entry 5242 (class 2606 OID 19749)
-- Name: data_quality_checks fk_quality_same_company; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.data_quality_checks
    ADD CONSTRAINT fk_quality_same_company FOREIGN KEY (application_id, company_id) REFERENCES public.credit_applications(application_id, company_id);


--
-- TOC entry 5265 (class 2606 OID 19769)
-- Name: application_data_requests fk_request_defined_field; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_data_requests
    ADD CONSTRAINT fk_request_defined_field FOREIGN KEY (product_code, field_code) REFERENCES public.application_field_requirements(product_code, field_code);


--
-- TOC entry 5266 (class 2606 OID 19764)
-- Name: application_data_requests fk_request_same_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_data_requests
    ADD CONSTRAINT fk_request_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);


--
-- TOC entry 5250 (class 2606 OID 19759)
-- Name: application_field_values fk_value_defined_field; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_values
    ADD CONSTRAINT fk_value_defined_field FOREIGN KEY (product_code, field_code) REFERENCES public.application_field_requirements(product_code, field_code);


--
-- TOC entry 5251 (class 2606 OID 19754)
-- Name: application_field_values fk_value_same_product; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.application_field_values
    ADD CONSTRAINT fk_value_same_product FOREIGN KEY (application_id, product_code) REFERENCES public.credit_applications(application_id, product_code);


--
-- TOC entry 5235 (class 2606 OID 19290)
-- Name: guarantors guarantors_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.guarantors
    ADD CONSTRAINT guarantors_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


--
-- TOC entry 5229 (class 2606 OID 19208)
-- Name: legal_events legal_events_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.legal_events
    ADD CONSTRAINT legal_events_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(company_id);


--
-- TOC entry 5278 (class 2606 OID 24605)
-- Name: risk_policy_parameters risk_policy_parameters_product_fk; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.risk_policy_parameters
    ADD CONSTRAINT risk_policy_parameters_product_fk FOREIGN KEY (product_code) REFERENCES public.credit_products(product_code);


--
-- TOC entry 5243 (class 2606 OID 19360)
-- Name: scoring_results scoring_results_application_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.scoring_results
    ADD CONSTRAINT scoring_results_application_id_fkey FOREIGN KEY (application_id) REFERENCES public.credit_applications(application_id);


-- Completed on 2026-10-23 23:59:11

--
-- PostgreSQL database dump complete
--

\unrestrict BvCZ5uGGSdxi1KYjmftb2p4JJWy0ZT2ydyIaS5AaqoHu1zZ0L7uWrUIeguqyy8U

