import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { ServerCabinet } from '../app/ServerPages';
import type { StateV2, ViewV2 } from '../api/HttpV2Api';

const seed = (id = 'case-a'): ViewV2 => ({
  case_id: id,
  version: 1,
  revision: 1,
  status: 'DRAFT',
  message: 'Серверная заявка',
  error_code: null,
  request: {
    borrower_id: 'company-40',
    legal_form: 'IP',
    amount_rub: 1500000,
    term_months: 12,
    purpose: 'INVENTORY',
  },
  selected_product_id: 'term',
  pending: null,
  history: [],
  product_selection: null,
  last_knowledge_answer: null,
  data_resolution: { gaps: [] },
  data_context: null,
  assessment: null,
  bank_application: null,
  allowed_actions: ['CHAT', 'UPDATE_REQUEST', 'SELECT_PRODUCT', 'LOOKUP_PROFILE'],
  allowed_operations: ['review', 'claim', 'authority', 'profile_resolution', 'review_changes'],
});
let cases: ViewV2[],
  role: 'BORROWER' | 'OPERATOR',
  mutations: Record<string, unknown>[],
  previews: Record<string, unknown>[];
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const state = (): StateV2 => ({
  session: {
    login: role === 'BORROWER' ? 'client01' : 'analyst',
    full_name: 'HTTP test',
    role,
    company_id: role === 'BORROWER' ? 40 : null,
  },
  cases: structuredClone(cases),
  companies: [{ company_id: 40, name: 'Серверная компания', inn: '123456789012' }],
  scopes: [],
  grants: [],
});
beforeEach(() => {
  cases = [seed()];
  role = 'BORROWER';
  mutations = [];
  previews = [];
  window.history.replaceState(null, '', '/');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = new URL(url, 'http://localhost').pathname.split('/').at(-1);
      const body = init?.body ? JSON.parse(String(init.body)) : {};
      if (path === 'session') return json(state().session);
      if (path === 'state') return json(state());
      if (path === 'operations') return json([]);
      if (path === 'operation') return json({ saved: true });
      if (path === 'catalog')
        return json({
          catalog_version: 'POSTGRES:test',
          candidates: Array.from({ length: 16 }, (_, i) => ({
            product_id: 'product-' + i,
            name: 'Направление ' + i,
            eligibility: 'UNKNOWN',
            database_supported: i < 3,
            reasons: [],
            source_version: 'POSTGRES:version-1',
            source_conditions: { validity: 'UNKNOWN', terms: [] },
          })),
        });
      if (path === 'audit') return json({ events: [], next_cursor: null, consent_events: [] });
      if (path === 'review-preview') {
        previews.push(body);
        return json({
          decision: body.arguments.decision,
          reason: body.arguments.reason,
          revision: 1,
          offer: { ...body.arguments.offer, schedule: [] },
        });
      }
      if (path === 'action') {
        mutations.push(body);
        if (body.command?.action === 'CREATE') {
          const c = seed('case-new');
          cases.push(c);
          return json(c);
        }
        if (body.kind === 'review') {
          cases[0].status = 'OFFERED';
          cases[0].version++;
          return json({ saved: true });
        }
        if (body.command?.action === 'UPDATE_REQUEST') {
          cases[0].request = { ...cases[0].request, ...body.command.arguments.patch };
          cases[0].version++;
          return json(cases[0]);
        }
        return json(cases[0]);
      }
      throw new Error('Unexpected HTTP path ' + path);
    }),
  );
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});
function open(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <ServerCabinet />
    </MemoryRouter>,
  );
}

it('labels a real monthly-logit attribution separately from the cumulative probability', async () => {
  cases[0].assessment = {
    status: 'DEMO_ESTIMATE',
    probability: 0.1,
    kind: 'CUMULATIVE_PD',
    horizon_months: 12,
    explanation: {
      status: 'AVAILABLE',
      method: 'CATBOOST_SHAP',
      space: 'RAW_MONTHLY_LOGIT',
      month_on_book: 1,
      source_ref: 'reviewed:source',
      note: 'Это не вклады в накопленную PD.',
      contributions: [{ feature: 'requested_amount', contribution: 0.2 }],
      base_value: -2,
      raw_output: -1.8,
    },
  };
  open('/client/applications/case-a');
  await screen.findByRole('heading', { name: 'Вклад факторов в логит месяца 1' });
  expect(screen.getByText('Это не вклады в накопленную PD.')).toBeInTheDocument();
  expect(screen.getByText('CATBOOST_SHAP · RAW_MONTHLY_LOGIT')).toBeInTheDocument();
});

it('loads the routed home from server state and creates one server case in the wizard', async () => {
  open('/client');
  await screen.findByRole('heading', { name: 'Финансирование вашего бизнеса' });
  expect(screen.getByText('Серверная компания')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Новая заявка' }));
  await screen.findByRole('heading', { name: 'Заявка на финансирование' });
  expect(mutations).toHaveLength(1);
  expect((mutations[0].command as { action: string }).action).toBe('CREATE');
  expect(screen.getByRole('navigation', { name: 'Шаги заявки' })).toBeInTheDocument();
});

it('keeps unsaved request values while moving between wizard steps', async () => {
  open('/client/new/case-a');
  await screen.findByLabelText('Сумма, ₽');
  fireEvent.change(screen.getByLabelText('Сумма, ₽'), { target: { value: '2100000' } });
  fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));
  await screen.findByText(/Шаг 2 из 4/);
  fireEvent.click(screen.getByRole('button', { name: 'Назад' }));
  await screen.findByText(/Шаг 1 из 4/);
  expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(2100000);
  expect(mutations).toHaveLength(0);
});

it('does not silently choose a purpose or legal form for a new request', async () => {
  cases[0].request = {
    borrower_id: 'company-40',
    legal_form: null,
    amount_rub: null,
    term_months: null,
    purpose: null,
  };
  open('/client/new/case-a');
  await screen.findByLabelText('Форма бизнеса');
  expect(screen.getByLabelText('Форма бизнеса')).toHaveValue('');
  expect(screen.getByLabelText('Цель')).toHaveValue('');
  expect(screen.getByLabelText('Цель')).toBeRequired();
});

it('does not substitute another case for an inaccessible deep link', async () => {
  open('/client/applications/foreign-case');
  await screen.findByRole('heading', { name: 'Заявка не найдена или недоступна' });
  expect(screen.queryByRole('button', { name: 'Сохранить параметры' })).not.toBeInTheDocument();
});

it('uses the PostgreSQL catalog with all directions and explicit unknown approval', async () => {
  open('/client/products');
  await screen.findByRole('heading', { name: 'Направление 15' });
  expect(screen.getAllByRole('heading', { level: 2 })).toHaveLength(16);
  expect(screen.getAllByText(/утверждённая policy неизвестна/)).toHaveLength(16);
  expect(screen.getAllByText('Бизнес-адаптер этого направления отсутствует')).toHaveLength(13);
});

it('filters the real bank queue by status and assignee without mock risk calculations', async () => {
  role = 'OPERATOR';
  cases = [
    { ...seed(), status: 'MANUAL_REVIEW', review_owner: 'analyst' },
    { ...seed('case-b'), status: 'NEEDS_INFO' },
  ];
  open('/bank/mine');
  await screen.findByRole('heading', { name: 'Очередь рассмотрения' });
  expect(screen.getByRole('link', { name: 'Разобрать' })).toHaveAttribute(
    'href',
    '/bank/applications/case-a',
  );
  fireEvent.change(screen.getByLabelText('Этап'), { target: { value: 'NEEDS_INFO' } });
  await screen.findByRole('heading', { name: 'По этому фильтру заявок нет' });
  expect(screen.queryByText(/1,3/)).not.toBeInTheDocument();
});

it('shows saved document coverage and duplicate periods in the documents route', async () => {
  cases[0].current_data = {
    questionnaire: [],
    documents: [
      {
        document_id: 'doc',
        filename: 'actual.csv',
        sha256: 'abc123',
        status: 'EXTRACTED_UNVERIFIED',
        statement: {
          status: 'CONFLICT',
          covered_months: 1,
          months: ['2026-09'],
          missing_months: ['2026-08'],
          duplicate_months: ['2026-09'],
          issues: [],
        },
      },
    ],
  };
  open('/client/documents');
  await screen.findByText('actual.csv');
  expect(screen.getByText(/Повторяющиеся периоды: 2026-09/)).toBeInTheDocument();
  expect(screen.getByText(/Полнота оборотов бизнеса и суммы не подтверждены/)).toBeInTheDocument();
});

it('previews a counteroffer without mutating, then explicitly confirms the same version', async () => {
  role = 'OPERATOR';
  cases[0].status = 'MANUAL_REVIEW';
  cases[0].bank_application = {
    status: 'MANUAL_REVIEW',
    offer: null,
    review_reasons: ['MANUAL_DECISION_REQUIRED'],
    execution: null,
  };
  open('/bank/applications/case-a');
  await screen.findByRole('button', { name: 'Предпросмотр решения' });
  fireEvent.change(screen.getByLabelText('Решение'), { target: { value: 'OFFERED' } });
  fireEvent.change(screen.getByLabelText('Обоснование'), {
    target: { value: 'Explicit synthetic counteroffer review' },
  });
  fireEvent.change(screen.getByLabelText('Сумма предложения, ₽'), { target: { value: '1000000' } });
  fireEvent.change(screen.getByLabelText('Ставка предложения, % годовых'), {
    target: { value: '20' },
  });
  fireEvent.change(screen.getByLabelText('Комиссии, ₽ (явно укажите 0, если нет)'), {
    target: { value: '50' },
  });
  fireEvent.change(screen.getByLabelText('Действует до'), {
    target: { value: '2027-01-01T12:00' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Предпросмотр решения' }));
  await screen.findByRole('button', { name: 'Подтвердить решение' });
  expect(previews).toHaveLength(1);
  expect(mutations).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Подтвердить решение' }));
  await waitFor(() => expect(mutations).toHaveLength(1));
  expect(mutations[0]).toMatchObject({
    kind: 'review',
    case_id: 'case-a',
    expected_version: 1,
    arguments: { decision: 'OFFERED', offer: { amount_rub: '1000000', fees_rub: ['50'] } },
  });
});

it('shows HTTP audit events and loads older pages instead of a synthetic history', async () => {
  role = 'OPERATOR';
  const actual = globalThis.fetch;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url.includes('/audit?'))
        return json({
          events: [
            {
              id: 1,
              case_id: 'case-a',
              actor_id: 'v2-analyst',
              action: 'verify',
              version: 9,
              revision: 4,
              created_at: '2026-10-25T12:00:00Z',
              metadata: { source_ref: 'real-document-ref' },
            },
          ],
          next_cursor: null,
          consent_events: [],
        });
      return actual(url, init);
    }),
  );
  open('/bank/journal');
  await screen.findByText('v2-analyst');
  expect(screen.getByText('verify')).toBeInTheDocument();
  expect(screen.getByText(/v9 · ревизия 4/)).toBeInTheDocument();
});
