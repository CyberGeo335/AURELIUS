import type { Status } from './status';
export type Product = 'R01' | 'R02' | 'R03';
export type Entity = 'IP' | 'OOO';
export type Profile = 'karpov' | 'zerno';
export type Scenario = 'normal' | 'missing' | 'external' | 'decline';
export const products: Record<Product, string> = {
  R01: 'Оборотный кредит',
  R02: 'Кредитная линия',
  R03: 'Овердрафт',
};
export interface Company {
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
  version: 1;
  companies: Company[];
  applications: Application[];
  storageError?: string;
}
export type BankAction = 'A' | 'B' | 'BOTH' | 'INFO' | 'DECLINE';
