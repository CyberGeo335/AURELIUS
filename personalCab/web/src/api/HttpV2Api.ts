export interface SessionV2 {
  login: string;
  full_name: string;
  role: 'BORROWER' | 'OPERATOR';
  company_id: number | null;
}
export interface CandidateV2 {
  product_id: string;
  name: string;
  eligibility: string;
  database_supported: boolean;
  reasons: string[];
  source_version?: string;
  source_url?: string;
  limitations?: string[];
  checks?: { code: string; label: string; status: string; reason: string; provenance: string }[];
  source_conditions?: {
    validity?: string;
    approval_version?: string;
    terms?: Record<string, unknown>[];
  };
}
export interface QuestionV2 {
  field_code: string;
  product_code: string;
  label: string;
  value: unknown;
  status: string;
  editable: boolean;
  data_type: string;
  source: string;
  source_ref?: string;
  available_at?: string;
  validation_error?: string;
}
export interface FollowUpV2 {
  request_id: string;
  fields: string[];
  documents: string[];
  reason: string;
  due_at: string | null;
  answered_fields: string[];
  answered_documents: string[];
  status: 'OPEN' | 'ANSWERED' | 'SUPERSEDED';
}
export interface PendingActionV2 {
  request_id: string;
  kind?: string;
  case_id?: string;
  expected_version?: number;
  command?: {
    request_id: string;
    action: string;
    case_id?: string;
    expected_version: number;
    text?: string;
    arguments?: Record<string, unknown>;
  };
  [key: string]: unknown;
}
export interface RecoveredOperationV2 {
  request_id: string;
  body: PendingActionV2;
  completed: boolean;
}
export interface OfferV2 {
  fees_rub: string[];
  offer_id: string;
  amount_rub: string;
  term_months: number;
  annual_rate_fraction: string;
  expires_at: string;
  conditions: string[];
  repayment_type: string;
  schedule: {
    month: number;
    payment: string;
    interest: string;
    principal: string;
    balance: string;
  }[];
}
export interface ViewV2 {
  case_id: string;
  version: number;
  revision: number;
  status: string;
  message: string;
  error_code: string | null;
  allowed_actions?: string[];
  action_reasons?: Record<string, string>;
  allowed_operations?: string[];
  follow_ups?: FollowUpV2[];
  checking_error?: string | null;
  created_at?: string;
  has_pending_changes?: boolean;
  review_owner?: string | null;
  business_profile?: {
    conflicts: string[];
    decision_at: string;
    verified_facts: { field: string; value: string; source_ref: string; available_at: string }[];
  } | null;
  authority_evidence?: {
    verified: boolean;
    source_ref: string;
    available_at: string;
    reviewed_by: string;
  } | null;
  client_changes?: {
    field: string;
    old_value: unknown;
    new_value: unknown;
    revision: number;
    source: string;
    review_status?: string;
  }[];
  field_changes?: {
    change_id: number;
    field_code: string;
    old_value: unknown;
    new_value: unknown;
    review_status: string;
    source_ref: string | null;
  }[];
  offer_history?: {
    offer: OfferV2;
    revision: number;
    reviewed_by: string;
    invalidated_at: string | null;
  }[];
  request: Record<string, string | number | boolean | null>;
  selected_product_id: string | null;
  pending: null | { proposal_id: string; patch: Record<string, unknown>; source_text: string };
  history: { role: string; content: string }[];
  product_selection: null | { candidates: CandidateV2[] };
  last_knowledge_answer: null | {
    source_sha256: string;
    citations: { field_code: string; source_ref: string; format_rule: string }[];
  };
  data_resolution: {
    database_lookup?: string;
    gaps: { field: string; reason: string; resolution: string; status?: string }[];
  };
  data_context: null | {
    questionnaire: QuestionV2[];
    snapshot_ids: Record<string, number>;
    documents: DocumentV2[];
    model_readiness: string;
    data_quality: { blocking_issues: string[] };
  };
  evidence_stale?: boolean;
  current_data?: {
    questionnaire: QuestionV2[];
    documents: DocumentV2[];
  } | null;
  assessment: null | {
    status: string;
    probability: number | null;
    kind?: string;
    horizon_months?: number;
    reasons?: string[];
    target?: string;
    model_id?: string;
    model_sha256?: string;
    registry_version?: string;
    validated_for_real_lending?: boolean;
    hazards?: number[];
    explanations?: { feature: string; contribution: number; source_ref?: string }[];
    explanation?: {
      status: string;
      reason?: string;
      method?: string;
      space?: string;
      month_on_book?: number;
      base_value?: number;
      raw_output?: number;
      source_ref?: string;
      note?: string;
      contributions?: { feature: string; contribution: number }[];
    };
    calculation?: {
      status: string;
      formula_version?: string;
      source_ref?: string;
      dscr?: string | null;
      monthly_payment_rub?: string;
      fees_rub?: string[] | null;
      threshold_applied?: number | null;
    };
  };
  bank_application: null | {
    status: string;
    offer: OfferV2 | null;
    review_reasons: string[];
    execution: null | { kind: string };
  };
}
export interface StateV2 {
  session: SessionV2;
  cases: ViewV2[];
  companies: { company_id: number; name: string; inn: string }[];
  scopes: string[];
  grants: { scope: string; expires_at: string; revoked: boolean }[];
}
export interface DocumentV2 {
  document_id: string;
  filename: string;
  status: string;
  sha256: string;
  statement?: {
    status: string;
    covered_months: number;
    months: string[];
    missing_months: string[];
    duplicate_months: string[];
    issues: string[];
  };
}
export interface AuditV2 {
  events: {
    id: number;
    case_id: string;
    actor_id: string;
    action: string;
    version: number;
    revision: number;
    created_at: string;
    metadata: Record<string, unknown>;
  }[];
  next_cursor: string | null;
  consent_events: {
    id: number;
    actor_id: string;
    company_id: number;
    action: string;
    scope: string;
    created_at: string;
  }[];
}
export class HttpV2Api {
  async request<T>(path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(
      () => controller.abort(),
      path === 'action' ? 180000 : body ? 60000 : 15000,
    );
    try {
      const response = await fetch('/api/v2/' + path, {
        signal: controller.signal,
        credentials: 'same-origin',
        headers: body ? { 'Content-Type': 'application/json' } : {},
        method: body ? 'POST' : 'GET',
        body: body ? JSON.stringify(body) : undefined,
      });
      const result = await response.json();
      if (!response.ok)
        throw Object.assign(
          new Error(
            response.status === 401
              ? 'Войдите в кабинет.'
              : response.status === 409
                ? result.code === 'STALE_CASE_VERSION'
                  ? 'Заявка изменилась. Ваш ввод сохранён; сверьте данные перед повтором.'
                  : (result.message ??
                    'Действие недоступно на текущем этапе. Обновите данные заявки.')
                : (result.message ?? result.error ?? 'Сервис временно недоступен.'),
          ),
          { status: response.status, code: result.code },
        );
      return result;
    } catch (e) {
      if (controller.signal.aborted)
        throw new Error('Сервис не ответил вовремя. Повторите запрос с прежним идентификатором.', {
          cause: e,
        });
      if (e instanceof TypeError)
        throw new Error(
          'Нет соединения с сервером. Ввод сохранён; повторите запрос после восстановления связи.',
          { cause: e },
        );
      throw e;
    } finally {
      clearTimeout(timer);
    }
  }
  session = () => this.request<SessionV2>('session');
  state = (detail?: string, summary = false) =>
    this.request<StateV2>(
      'state' +
        (summary ? '?summary=1' + (detail ? '&detail=' + encodeURIComponent(detail) : '') : ''),
    );
  login = (login: string, password: string) => this.request('login', { login, password });
  logout = () => this.request('logout', {});
  action = (body: unknown) => this.request<ViewV2>('action', body);
  operations = () => this.request<RecoveredOperationV2[]>('operations');
  prepare = (body: PendingActionV2) => this.request('operation', { operation: 'prepare', body });
  acknowledge = (request_id: string) =>
    this.request('operation', { operation: 'acknowledge', request_id });
  catalog = () =>
    this.request<{
      candidates: CandidateV2[];
      catalog_version: string;
      model_registry?: { version: string; available: boolean; models: Record<string, unknown>[] };
    }>('catalog');
  audit = (caseId?: string, cursor?: string) =>
    this.request<AuditV2>(
      'audit?' +
        new URLSearchParams({
          ...(caseId ? { case_id: caseId } : {}),
          ...(cursor ? { cursor } : {}),
        }),
    );
  preview = (body: unknown) =>
    this.request<{ offer?: OfferV2; decision: string; reason: string; revision: number }>(
      'review-preview',
      body,
    );
}
