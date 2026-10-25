import type { CreditApi, DraftPatch } from './CreditApi';
import type {
  Application,
  AssistantFacts,
  BankAction,
  Company,
  CreditState,
  Product,
  Profile,
  RequestOptions,
  ServerApplication,
  ServerRequirement,
} from '../domain/types';
import { HttpV2Api } from './HttpV2Api';

export interface BusinessState {
  companies: Record<string, unknown>[];
  applications: ServerApplication[];
  requirements: ServerRequirement[];
  catalog: Record<string, unknown>[];
}
export class HttpCreditApi implements CreditApi {
  private state: CreditState = { version: 1, companies: [], applications: [] };
  private listeners = new Set<() => void>();
  private pending = new Map<string, Record<string, unknown>>();
  private enabled = false;
  private lastRefresh = 0;
  private generation = 0;
  constructor(private http = new HttpV2Api()) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  clear = () => {
    this.enabled = false;
    this.generation++;
    this.pending.clear();
    this.state = { version: 1, companies: [], applications: [] };
    this.listeners.forEach((listener) => listener());
  };
  refresh = async () => {
    const generation = this.generation;
    const data = await this.http.request<BusinessState>('state');
    if (generation !== this.generation) return;
    const companies: Company[] = data.companies.map((c) => ({
      id: String(c.company_id),
      name: String(c.name ?? ''),
      inn: String(c.inn ?? ''),
      entity: c.entity_type === 'INDIVIDUAL_ENTREPRENEUR' ? 'IP' : 'OOO',
      registration: String(c.ogrn ?? c.ogrnip ?? ''),
      registered: String(c.registration_date ?? ''),
      okved: String(c.okved_main ?? ''),
      flow: 0,
      existing: 0,
      monthly: [],
      server: c,
    }));
    this.state = {
      version: 1,
      companies,
      applications: data.applications.map(project),
      requirements: data.requirements,
      catalog: data.catalog,
    };
    this.enabled = true;
    this.lastRefresh = Date.now();
    this.listeners.forEach((listener) => listener());
  };
  command = async (action: string, id?: string, arguments_: Record<string, unknown> = {}) => {
    const app = this.state.applications.find((a) => a.id === id);
    const body = {
      kind: 'credit',
      action,
      ...(id ? { application_id: Number(id), expected_version: app?.revision } : {}),
      ...arguments_,
    };
    const key = JSON.stringify({ action, id, arguments_ });
    const request = this.pending.get(key) ?? { ...body, request_id: crypto.randomUUID() };
    this.pending.set(key, request);
    try {
      const result = await this.http.request<{ application_id: string }>('action', request);
      this.pending.delete(key);
      await this.refresh();
      return result.application_id;
    } catch (error) {
      const status = (error as { status?: number }).status;
      if (status && status < 500) this.pending.delete(key);
      // A scoring outage can happen after submission committed. Restore the real state.
      await this.refresh().catch(() => {});
      throw error;
    }
  };
  createDraft = async (_profile: Profile, product: Product) =>
    this.command('create', undefined, { product });
  saveDraft = async (id: string, patch: DraftPatch) => {
    await this.command('save', id, { patch });
  };
  submit = async (id: string) => {
    await this.command('submit', id);
  };
  revise = async (id: string, amount: number, term: number) => {
    await this.command('revise', id, { amount, term });
  };
  answerRequest = async (id: string, requestId: string, answer: string, file?: string) => {
    if (file)
      throw new Error('Для ответа используйте поле анкеты. Загрузка документов ещё не подключена.');
    await this.command('answer', id, { data_request_id: Number(requestId), answer });
  };
  bankDecision = async (
    id: string,
    _revision: number,
    action: BankAction,
    reason: string,
    request?: RequestOptions,
  ) => {
    if (action === 'B' || action === 'BOTH')
      throw new Error('Доступно одно рассчитанное предложение.');
    await this.command('review', id, {
      decision: action === 'A' ? 'APPROVE' : action === 'INFO' ? 'REQUEST_DATA' : 'REJECT',
      reason,
      field_code: request?.field,
    });
  };
  resolveData = async (
    id: string,
    kind: 'authority' | 'revenue',
    comment: string,
    sourceRef?: string,
  ) => {
    if (!sourceRef?.trim()) throw new Error('Укажите источник проверки.');
    await this.command('verify', id, { check_kind: kind, comment, source_ref: sourceRef });
  };
  applyAssistant = async (
    _profile: Profile,
    _product: Product,
    _facts: AssistantFacts,
  ): Promise<string> => {
    throw new Error('Подключение ассистента — следующий этап интеграции.');
  };
  accept = async (id: string, offerId: string) => {
    await this.command('accept', id, { offer_id: Number(offerId) });
  };
  sign = async (_id: string) => {
    throw new Error('Сценарий завершается принятием предложения.');
  };
  fund = this.sign;
  cancel = async (id: string) => {
    await this.command('cancel', id);
  };
  reset = async () => {
    throw new Error('Сброс доступен только в mock-режиме.');
  };
  tick = async () => {
    if (this.enabled && Date.now() - this.lastRefresh > 5000) await this.refresh();
  };
}

function project(a: ServerApplication): Application {
  const offer = a.offer
    ? {
        id: String(a.offer.offer_id),
        revision: a.version,
        amount: Number(a.offer.offered_amount),
        term: a.offer.offered_term_months,
        expires: Infinity,
        kind: 'OFFER' as const,
        label: 'Предложение банка',
      }
    : undefined;
  return {
    id: String(a.application_id),
    companyId: String(a.company_id),
    product: a.product_code,
    amount: Number(a.requested_amount ?? 0),
    term: a.requested_term_months ?? 0,
    purpose: a.purpose ?? '',
    status: a.application_status,
    decision: a.decision,
    offerStatus: a.offer?.offer_status,
    stage: a.application_status === 'DRAFT' ? 0 : a.application_status === 'APPROVED' ? 5 : 2,
    revision: a.version,
    created: Date.parse(a.application_date),
    updated: Date.parse(a.application_date),
    scenario: 'normal',
    externalWait: false,
    fields: Object.fromEntries(a.fields.map((f) => [f.field_code, String(f.field_value ?? '')])),
    sources: Object.fromEntries(a.fields.map((f) => [f.field_code, f.value_source])),
    flow: 0,
    existing: 0,
    leasing: null,
    businessConfirmed: a.form_state.businessConfirmed === true,
    statement: false,
    consentBki: a.form_state.consentBki === true,
    consentData: a.form_state.consentData === true,
    offers: offer ? [offer] : [],
    acceptedOffer: a.offer?.offer_status === 'ACCEPTED' ? offer : undefined,
    requests: a.requests.map((r) => ({
      id: String(r.request_id),
      field: r.field_code,
      text: r.question_text,
      state: r.request_status === 'OPEN' ? 'OPEN' : 'CLOSED',
    })),
    history: [],
    revisions: [],
    reason: a.reasons
      .map((r) => r.message)
      .filter(Boolean)
      .join('\n'),
    reasonCode: a.reasons.map((r) => r.code).join(', '),
    step: Number(a.form_state.step ?? 0),
    files: [],
    server: a,
  };
}
