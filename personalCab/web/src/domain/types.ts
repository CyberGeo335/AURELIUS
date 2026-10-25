import type { Status } from './status';
export type Product = 'R01' | 'R02' | 'R03';
export type Entity = 'IP' | 'OOO';
export type Profile = string;
export type Scenario = 'normal' | 'missing' | 'external' | 'decline';
export const products: Record<Product, string> = {
  R01: 'Оборотный кредит',
  R02: 'Кредитная линия',
  R03: 'Овердрафт',
};
export interface Company {
  server?: Record<string, unknown>;
  id: string;
  entity: Entity;
  name: string;
  inn: string;
  registration: string;
  registered: string;
  okved: string;
  flow: number;
  existing: number;
  monthly: number[];
}
export interface Audit {
  id: string;
  at: number;
  actor: string;
  text: string;
  revision: number;
  model: string;
  policy: string;
  snapshot: string;
}
export interface Offer {
  id: string;
  revision: number;
  amount: number;
  term: number;
  expires: number;
  kind: 'OFFER' | 'COUNTEROFFER';
  label: string;
}
export interface DataRequest {
  id: string;
  field: string;
  text: string;
  state: 'OPEN' | 'CLOSED';
  answer?: string;
  file?: string;
  reason?: string;
  dueAt?: number;
}
export interface Revision {
  revision: number;
  at: number;
  amount: number;
  term: number;
  fields: Record<string, string>;
  reason: string;
}
export interface Application {
  id: string;
  companyId: string;
  product: Product;
  amount: number;
  term: number;
  purpose: string;
  status: Status;
  decision?: 'APPROVE' | 'REJECT' | 'REQUEST_DATA' | 'MANUAL_REVIEW';
  offerStatus?: 'DRAFT' | 'PROPOSED' | 'ACCEPTED' | 'DECLINED';
  /** Mock-only demo playback; never persisted to the business DB. */
  demoExecution?: 'SIGNED_DEMO' | 'FUNDED_DEMO';
  server?: ServerApplication;
  stage: number;
  revision: number;
  created: number;
  updated: number;
  nextAt?: number;
  scenario: Scenario;
  externalWait: boolean;
  fields: Record<string, string>;
  sources: Record<string, string>;
  flow: number;
  existing: number;
  leasing: boolean | null;
  businessConfirmed: boolean;
  statement: boolean;
  consentBki: boolean;
  consentData: boolean;
  consentVersion?: string;
  consentedAt?: number;
  offers: Offer[];
  acceptedOffer?: Offer;
  requests: DataRequest[];
  history: Audit[];
  revisions: Revision[];
  reason: string;
  reasonCode: string;
  step: number;
  furthestStep?: number;
  owner?: string;
  files: string[];
  monthly?: number[];
  statementMonths?: string[];
  originalFields?: Record<string, string>;
  fieldStatuses?: Record<string, 'CONFIRMED' | 'UNVERIFIED' | 'CONFLICT' | 'STALE'>;
  sourceDate?: number;
  checks?: { authority: boolean; revenue: boolean; comment: string };
  assistantCaseId?: string;
  assistantMessageIds?: string[];
}
export interface AssistantFacts {
  amount?: number;
  term?: number;
  purpose?: string;
  caseId?: string;
  messageId: string;
  applicationId?: string;
}
export interface RequestOptions {
  field: string;
  dueAt: number;
}
export interface CreditState {
  requirements?: ServerRequirement[];
  catalog?: Record<string, unknown>[];
  version: 1;
  companies: Company[];
  applications: Application[];
  storageError?: string;
}
export type BankAction = 'A' | 'B' | 'BOTH' | 'INFO' | 'DECLINE';

export interface ServerApplication {
  offer_stale?: { reason: string } | null;
  assignment?: {
    employee_id: number;
    first_name: string;
    last_name: string;
    assigned_at: string;
  } | null;
  documents?: {
    document_id: number;
    application_id: number;
    uploaded_by: number;
    data_request_id: number | null;
    filename: string;
    media_type: string;
    size: number;
    sha256: string;
    source: 'CLIENT_UPLOAD' | 'EMPLOYEE_UPLOAD';
    processing_status: 'STORED_UNVERIFIED';
    created_at: string;
  }[];
  verifications?: {
    details: { kind: 'authority' | 'revenue'; source_ref: string; comment: string };
    created_at: string;
    first_name: string;
    last_name: string;
  }[];
  application_id: number;
  company_id: number;
  product_code: Product;
  requested_amount: string | null;
  requested_term_months: number | null;
  purpose: string | null;
  application_status: Status;
  application_date: string;
  version: number;
  decision: Application['decision'];
  reasons: { code: string; message: string }[];
  offer: {
    offer_id: number;
    offer_status: Application['offerStatus'];
    offered_amount: string;
    offered_term_months: number;
    offered_annual_rate_pct: string;
  } | null;
  assessment: {
    risk_assessment?: { pd_application_1y?: number | null; pd_limit_1y?: number | null };
    offer?: { max_monthly_payment?: string; monthly_schedule?: unknown[] };
    policy_version?: string;
  } | null;
  fields: {
    field_code: string;
    field_value: unknown;
    verification_status: string;
    value_source: string;
  }[];
  details: Record<string, unknown> | null;
  product_details: Record<string, unknown> | null;
  form_state: Record<string, unknown>;
  requests: {
    request_id: number;
    field_code: string;
    question_text: string;
    request_status: string;
    answer_value: unknown;
  }[];
  history: { event_id: number; action: string; created_at: string }[];
}
export interface ServerRequirement {
  product_code: Product;
  field_number: number;
  field_code: string;
  field_label: string;
  required_ip: boolean;
  required_ooo: boolean;
  target_db_field: string;
  format_rule: string | null;
}
