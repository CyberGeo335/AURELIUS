import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { IntegratedCabinet } from '../app/IntegratedCabinet';
import type { StateV2, ViewV2 } from '../api/HttpV2Api';

const view = (id = 'case-a'): ViewV2 => ({
  case_id: id,
  version: 1,
  revision: 1,
  status: 'DRAFT',
  message: 'Серверная заявка',
  error_code: null,
  allowed_actions: [
    'CHAT',
    'UPDATE_REQUEST',
    'SELECT_PRODUCT',
    'CONFIRM_FACTS',
    'CANCEL',
    'REFRESH_EVIDENCE',
    'ASSESS',
    'SUBMIT',
    'POLL_STATUS',
    'ACCEPT_OFFER',
    'EXECUTE_DEMO',
  ],
  allowed_operations: ['fields', 'document', 'payment', 'verify', 'features', 'review'],
  request: { legal_form: 'IP', amount_rub: 1500000, term_months: 12, purpose: 'INVENTORY' },
  selected_product_id: 'term',
  pending: null,
  history: [],
  product_selection: null,
  last_knowledge_answer: null,
  data_resolution: { gaps: [] },
  data_context: null,
  assessment: null,
  bank_application: null,
});
let login: string | null;
let cases: ViewV2[];
let actions: Array<Record<string, unknown>>;
let onAction: (body: Record<string, unknown>) => Response | Promise<Response>;
let poll: () => void;
let journal: Map<string, { login: string; body: Record<string, unknown> }>;
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status });
const currentState = (): StateV2 => ({
  session: {
    login: login!,
    full_name: login!,
    role: 'BORROWER',
    company_id: login === 'client01' ? 40 : 41,
  },
  cases: structuredClone(cases),
  companies: [],
  scopes: [],
  grants: [],
});
const actionCommand = (body: Record<string, unknown>) =>
  body.command as {
    action: string;
    request_id: string;
    expected_version: number;
    text?: string;
    arguments?: { patch?: Record<string, string | number | boolean | null> };
  };
async function openCabinet() {
  const mounted = render(
    <MemoryRouter>
      <IntegratedCabinet />
    </MemoryRouter>,
  );
  await screen.findByText('client01 · Клиент');
  await waitFor(() =>
    expect(screen.getByRole('button', { name: 'Сохранить параметры' })).toBeEnabled(),
  );
  return mounted;
}
async function signInSecondClient() {
  await screen.findByRole('heading', { name: 'Вход в кабинет' });
  fireEvent.change(screen.getByLabelText('Логин'), { target: { value: 'client02' } });
  fireEvent.change(screen.getByLabelText('Пароль'), { target: { value: 'test-only' } });
  fireEvent.click(screen.getByRole('button', { name: 'Войти' }));
  await screen.findByText('client02 · Клиент');
}
beforeEach(() => {
  window.history.replaceState(null, '', '/');
  login = 'client01';
  cases = [view()];
  actions = [];
  journal = new Map();
  onAction = () => json(cases[0]);
  const realInterval = globalThis.setInterval,
    realClear = globalThis.clearInterval;
  vi.spyOn(globalThis, 'setInterval').mockImplementation(((
    callback: () => void,
    delay?: number,
  ) => {
    if (delay === 5000) {
      poll = callback;
      return -1;
    }
    return realInterval(callback, delay);
  }) as typeof setInterval);
  vi.spyOn(globalThis, 'clearInterval').mockImplementation((id) => {
    if (Number(id) !== -1) realClear(id);
  });
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const path = url.split('/').at(-1);
      if (path === 'logout') {
        login = null;
        return json({ authenticated: false });
      }
      if (path === 'login') {
        login = 'client02';
        cases = [view('case-b')];
        return json({ authenticated: true });
      }
      if (!login) return json({ error: 'LOGIN_REQUIRED' }, 401);
      if (path === 'session') return json(currentState().session);
      if (path === 'state') return json(currentState());
      if (path === 'operations')
        return json(
          [...journal.values()]
            .filter((item) => item.login === login)
            .map(({ body }) => ({
              request_id: body.request_id,
              body,
              completed: false,
            })),
        );
      if (path === 'operation') {
        const operation = JSON.parse(String(init?.body));
        if (operation.operation === 'prepare')
          journal.set(operation.body.request_id, { login: login!, body: operation.body });
        else journal.delete(operation.request_id);
        return json({ saved: true });
      }
      if (path === 'action') {
        const body = JSON.parse(String(init?.body));
        actions.push(body);
        return onAction(body);
      }
      throw new Error('Unexpected endpoint');
    }),
  );
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Integrated HTTP cabinet regressions', () => {
  const withQuestionnaire = (id: string, value: string | null = null): ViewV2 => ({
    ...view(id),
    data_context: {
      snapshot_ids: { R01: 1 },
      documents: [],
      model_readiness: 'INSUFFICIENT_DATA',
      data_quality: { blocking_issues: [] },
      questionnaire: [
        {
          field_code: 'R01_07',
          product_code: 'R01',
          label: 'Залог',
          value,
          status: value ? 'REPORTED' : 'MISSING',
          editable: true,
          data_type: 'text',
          source: 'CLIENT',
        },
        {
          field_code: 'R01_08',
          product_code: 'R01',
          label: 'Поручитель',
          value: null,
          status: 'MISSING',
          editable: true,
          data_type: 'boolean',
          source: 'CLIENT',
        },
      ],
    },
  });
  it('does not carry questionnaire inputs to another case', async () => {
    cases = [withQuestionnaire('case-a'), withQuestionnaire('case-b', 'Server B')];
    await openCabinet();
    fireEvent.change(screen.getByLabelText(/Залог/), { target: { value: 'Unsaved case A' } });
    fireEvent.click(screen.getByRole('button', { name: /case-b ·/ }));
    expect(screen.getByLabelText(/Залог/)).toHaveValue('Server B');
    fireEvent.click(screen.getByRole('button', { name: /case-a ·/ }));
    expect(screen.getByLabelText(/Залог/)).toHaveValue('');
  });
  it('shows saved answers separately from the old immutable snapshot', async () => {
    cases = [withQuestionnaire('case-a')];
    onAction = (body) => {
      const value = (body.answers as { value: string }[])[0].value;
      cases[0].version++;
      cases[0].current_data = {
        questionnaire: [{ ...cases[0].data_context!.questionnaire[0], value, status: 'REPORTED' }],
        documents: [],
      };
      return json({ saved: true });
    };
    await openCabinet();
    fireEvent.change(screen.getByLabelText(/Залог/), { target: { value: 'Saved answer' } });
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить ответы' }));
    await screen.findByLabelText(/Залог · REPORTED/);
    expect(screen.getByLabelText(/Залог/)).toHaveValue('Saved answer');
    expect(cases[0].data_context!.questionnaire[0].value).toBeNull();
  });
  it('disables actions according to the server projection', async () => {
    cases[0].allowed_actions = ['CHAT'];
    cases[0].action_reasons = { ASSESS: 'Нужны проверенные входы.' };
    render(
      <MemoryRouter>
        <IntegratedCabinet />
      </MemoryRouter>,
    );
    await screen.findByText('client01 · Клиент');
    expect(screen.getByRole('button', { name: 'Запустить оценку' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Сохранить параметры' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Отменить обращение' })).toBeDisabled();
    expect(screen.getByText('Оценка: Нужны проверенные входы.')).toBeInTheDocument();
  });
  it('shows actual model horizon, target and missing-input reasons', async () => {
    cases[0].assessment = {
      status: 'INSUFFICIENT_DATA',
      probability: null,
      reasons: ['VERIFIED_FEATURE_INPUT_REQUIRED'],
    };
    const mounted = await openCabinet();
    expect(screen.getByText('Нужны проверенные сотрудником входы модели.')).toBeInTheDocument();
    cases[0].assessment = {
      status: 'DEMO_ESTIMATE',
      probability: 0.13,
      kind: 'ONE_MONTH_HAZARD',
      horizon_months: 1,
      target: 'Synthetic target',
      model_id: 'synthetic-model',
      registry_version: 'test-1',
    };
    await act(async () => poll());
    expect(screen.getByText('Горизонт: 1 мес.')).toBeInTheDocument();
    expect(screen.getByText(/Цель модели: Synthetic target/)).toHaveTextContent('synthetic-model');
    mounted.unmount();
  });
  it('shows polling errors and preserves drafts until synchronization succeeds', async () => {
    await openCabinet();
    fireEvent.change(screen.getByLabelText('Сумма, ₽'), { target: { value: '999999' } });
    vi.mocked(fetch).mockResolvedValueOnce(json({ error: 'STORAGE_UNAVAILABLE' }, 503));
    await act(async () => poll());
    expect(await screen.findByText(/Показано последнее полученное состояние/)).toBeInTheDocument();
    expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(999999);
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await waitFor(() =>
      expect(screen.queryByText(/Показано последнее полученное состояние/)).not.toBeInTheDocument(),
    );
    expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(999999);
  });
  it('distinguishes initial server failure from an unauthenticated login', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(json({ error: 'STORAGE_UNAVAILABLE' }, 503));
    render(
      <MemoryRouter>
        <IntegratedCabinet />
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Нет соединения с кабинетом' });
    expect(screen.queryByLabelText('Пароль')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    await screen.findByText('client01 · Клиент');
  });
  it('recovers the identical operation after a reload without automatically executing it', async () => {
    onAction = () => {
      cases[0].version = 2;
      throw new TypeError('Connection lost after commit');
    };
    const mounted = await openCabinet();
    fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
    fireEvent.change(screen.getByLabelText('Сообщение'), {
      target: { value: 'Recover this exact message' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await screen.findByRole('button', { name: 'Повторить' });
    expect(journal.size).toBe(1);
    mounted.unmount();
    onAction = () => json(cases[0]);
    await openCabinet();
    const restore = await screen.findByRole('button', { name: 'Восстановить и повторить' });
    expect(actions).toHaveLength(1);
    fireEvent.click(restore);
    await waitFor(() => expect(actions).toHaveLength(2));
    expect(actions[1]).toEqual(actions[0]);
    await waitFor(() => expect(journal.size).toBe(0));
  });
  it.each([{ fees: ['12345.67'] }, { fees: [] }])(
    'discloses offer fees before acceptance: $fees',
    async ({ fees }) => {
      cases[0].status = 'OFFERED';
      cases[0].bank_application = {
        status: 'OFFERED',
        review_reasons: [],
        execution: null,
        offer: {
          offer_id: 'offer-a',
          amount_rub: '1500000',
          term_months: 12,
          annual_rate_fraction: '0.24',
          fees_rub: fees,
          expires_at: '2099-01-01T00:00:00Z',
          conditions: [],
          repayment_type: 'ANNUITY',
          schedule: [],
        },
      };
      await openCabinet();
      expect(screen.getByText(/Комиссии:/)).toHaveTextContent(
        fees.length ? /12\s345,67\s₽/ : /0,00\s₽/,
      );
      expect(screen.getByRole('button', { name: 'Принять предложение DEMO' })).toBeVisible();
    },
  );

  it.each(['logout', 'expired', 'changed'] as const)(
    'clears account drafts on %s',
    async (mode) => {
      await openCabinet();
      fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
      fireEvent.change(screen.getByLabelText('Сообщение'), {
        target: { value: 'Private draft client01' },
      });
      if (mode === 'changed') {
        login = 'client02';
        cases = [view('case-b')];
        await act(async () => poll());
        await screen.findByText('client02 · Клиент');
      } else {
        if (mode === 'logout') fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
        else {
          login = null;
          await act(async () => poll());
        }
        await signInSecondClient();
      }
      expect(screen.queryByLabelText('Сообщение')).not.toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
      expect(screen.getByLabelText('Сообщение')).toHaveValue('');
      expect(window.location.search).toBe('?case=case-b');
    },
  );

  it('clears unsaved request parameters on logout', async () => {
    await openCabinet();
    fireEvent.change(screen.getByLabelText('Сумма, ₽'), { target: { value: '999999' } });
    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    await signInSecondClient();
    expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(1500000);
  });

  it('preserves the draft base version when polling receives concurrent edits', async () => {
    onAction = (body) => {
      expect(actionCommand(body).expected_version).toBe(1);
      return json({ code: 'STALE_CASE_VERSION' }, 409);
    };
    await openCabinet();
    fireEvent.change(screen.getByLabelText('Сумма, ₽'), { target: { value: '987654' } });
    cases[0].version = 2;
    cases[0].request.amount_rub = 2000000;
    await act(async () => poll());
    expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(987654);
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить параметры' }));
    await screen.findByRole('button', { name: 'Повторить на актуальной версии' });
    expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(987654);
  });

  it.each(['CHAT', 'UPDATE_REQUEST'])(
    'preserves input and explicitly rebases %s after 409',
    async (action) => {
      onAction = (body) => {
        const cmd = actionCommand(body);
        if (actions.length === 1) {
          cases[0].version = 2;
          cases[0].request.amount_rub = 2000000;
          return json({ code: 'STALE_CASE_VERSION' }, 409);
        }
        expect(cmd.expected_version).toBe(2);
        cases[0].version = 3;
        if (cmd.arguments?.patch) Object.assign(cases[0].request, cmd.arguments.patch);
        return json(cases[0]);
      };
      await openCabinet();
      fireEvent.change(screen.getByLabelText('Сумма, ₽'), { target: { value: '987654' } });
      fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
      fireEvent.change(screen.getByLabelText('Сообщение'), {
        target: { value: 'Keep my question' },
      });
      fireEvent.click(
        screen.getByRole('button', {
          name: action === 'CHAT' ? 'Отправить' : 'Сохранить параметры',
        }),
      );
      const repeat = await screen.findByRole('button', { name: 'Повторить на актуальной версии' });
      expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(987654);
      expect(screen.getByLabelText('Сообщение')).toHaveValue('Keep my question');
      expect(screen.getByText(/Текущие параметры сервера:/)).toHaveTextContent('2000000');
      expect(screen.queryByRole('button', { name: 'Повторить' })).not.toBeInTheDocument();
      fireEvent.click(repeat);
      await waitFor(() => expect(actions).toHaveLength(2));
      await waitFor(() =>
        expect(
          screen.queryByRole('button', { name: 'Повторить на актуальной версии' }),
        ).not.toBeInTheDocument(),
      );
      expect(actions[1].request_id).not.toBe(actions[0].request_id);
      expect(actionCommand(actions[1]).request_id).not.toBe(actionCommand(actions[0]).request_id);
      expect(screen.getByLabelText('Сумма, ₽')).toHaveValue(987654);
      await waitFor(() =>
        expect(screen.getByLabelText('Сообщение')).toHaveValue(
          action === 'CHAT' ? '' : 'Keep my question',
        ),
      );
    },
  );

  it('replays identical IDs for an unknown network outcome instead of rebasing', async () => {
    onAction = () => {
      if (actions.length === 1) {
        cases[0].version = 2;
        throw new TypeError('Network interrupted');
      }
      return json(cases[0]);
    };
    await openCabinet();
    fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
    fireEvent.change(screen.getByLabelText('Сообщение'), {
      target: { value: 'Keep on network error' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Повторить' }));
    await waitFor(() => expect(actions).toHaveLength(2));
    expect(actions[1]).toEqual(actions[0]);
    await waitFor(() => expect(screen.getByLabelText('Сообщение')).toHaveValue(''));
  });

  it('discards a late action response after another user has signed in', async () => {
    let finish!: (response: Response) => void;
    onAction = () =>
      new Promise((resolve) => {
        finish = resolve;
      });
    await openCabinet();
    fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
    fireEvent.change(screen.getByLabelText('Сообщение'), { target: { value: 'Old operation' } });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await waitFor(() => expect(actions).toHaveLength(1));
    fireEvent.click(screen.getByRole('button', { name: 'Выйти' }));
    await signInSecondClient();
    fireEvent.click(screen.getByRole('button', { name: 'Помощник' }));
    fireEvent.change(screen.getByLabelText('Сообщение'), { target: { value: 'New user draft' } });
    await act(async () => finish(json(view('case-a'))));
    expect(screen.getByText('client02 · Клиент')).toBeInTheDocument();
    expect(screen.getByLabelText('Сообщение')).toHaveValue('New user draft');
    expect(window.location.search).toBe('?case=case-b');
  });
});
