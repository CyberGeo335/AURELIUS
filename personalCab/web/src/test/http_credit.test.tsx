import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { HttpAuthApi } from '../api/HttpAuthApi';
import { HttpCreditApi } from '../api/HttpCreditApi';
import { Providers } from '../app/context';
import { App } from '../app/App';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const user = {
  user_id: 10,
  first_name: 'Иван',
  last_name: 'Иванов',
  login: 'client-db',
  role: 'CLIENT',
  company_id: 123,
};
const application = {
  application_id: 456,
  company_id: 123,
  product_code: 'R01',
  requested_amount: '3000000',
  requested_term_months: 36,
  purpose: 'Пополнение оборотных средств',
  application_status: 'APPROVED',
  application_date: '2026-10-26T10:00:00Z',
  version: 2,
  form_state: {},
  decision: 'APPROVE',
  reasons: [{ code: 'BANK_APPROVE', message: 'Условия проверены сотрудником.' }],
  offer: {
    offer_id: 25,
    offer_status: 'PROPOSED',
    offered_amount: '2500000',
    offered_term_months: 36,
    offered_annual_rate_pct: '28.00',
  },
  fields: [],
  requests: [],
  history: [],
  details: null,
  product_details: null,
  // Defence in depth: the client screen never renders risk even in a malformed response.
  assessment: { risk_assessment: { pd_application_1y: 0.131757, pd_limit_1y: 0.2 } },
};
const state = {
  companies: [
    { company_id: 123, name: 'Компания из БД', entity_type: 'LEGAL_ENTITY', inn: '7701000000' },
  ],
  applications: [application],
  requirements: [],
  catalog: [],
};

describe('HTTP stage tracks', () => {
  const requirement = {
    product_code: 'R01',
    field_number: 3,
    field_code: 'R01_03',
    field_label: 'ИНН',
    required_ooo: true,
    required_ip: true,
    target_db_field: 'companies.inn',
    format_rule: null,
  };
  const checking = {
    ...application,
    application_status: 'UNDER_REVIEW',
    decision: 'MANUAL_REVIEW',
    offer: null,
    assessment: null,
    fields: [
      {
        field_code: 'R01_03',
        field_value: '7701000000',
        verification_status: 'VERIFIED',
        value_source: 'BANK',
      },
    ],
    assignment: {
      employee_id: 10,
      first_name: 'Иван',
      last_name: 'Иванов',
      assigned_at: '2026-10-26',
    },
  };
  function mount(path: string, app = checking) {
    vi.stubEnv('VITE_API_MODE', 'http');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        Response.json(
          url.endsWith('session')
            ? path.startsWith('/bank')
              ? { ...user, role: 'BANK_EMPLOYEE', company_id: null }
              : user
            : { ...state, applications: [app], requirements: [requirement] },
        ),
      ),
    );
    render(
      <MemoryRouter initialEntries={[path]}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
  }
  it.each([
    ['/client', true],
    ['/client/applications/456', false],
    ['/bank', true],
    ['/bank/mine', true],
    ['/bank/applications/456', false],
  ] as const)('restores the existing track at %s (mini=%s)', async (path, mini) => {
    mount(path);
    const tracks = await screen.findAllByRole('list', { name: 'Этапы обработки' });
    const track =
      path === '/client' ? tracks.find((t) => t.classList.contains('mini'))! : tracks[0];
    expect(track.classList.contains('mini')).toBe(mini);
    const steps = track.querySelectorAll('.chevron');
    expect(steps).toHaveLength(path.startsWith('/bank') ? 6 : 5);
    expect(steps[1]).toHaveClass('done');
    expect(steps[2]).toHaveClass('future');
    expect(steps[2]).toHaveAttribute('title', expect.stringContaining('Нет подтверждения'));
    if (path.startsWith('/bank')) expect(steps[5]).toHaveTextContent('Решение · стоп');
    else expect(steps[3]).toHaveClass('future');
  });
  it.each(['DRAFT', 'CANCELLED'])('does not render a track for %s', async (application_status) => {
    mount('/client/applications/456', { ...checking, application_status });
    await screen.findByRole('heading', { name: 'Причины решения' });
    expect(screen.queryByRole('list', { name: 'Этапы обработки' })).not.toBeInTheDocument();
  });
  it('renders refusal without pretending the intermediate stages completed', async () => {
    mount('/client/applications/456', {
      ...checking,
      application_status: 'REJECTED',
      decision: 'REJECT',
    });
    const track = await screen.findByRole('list', { name: 'Этапы обработки' });
    expect(track.querySelectorAll('.done')).toHaveLength(0);
    expect(track.querySelectorAll('.current')).toHaveLength(1);
    expect(screen.getByText('Решение: отказ')).toBeInTheDocument();
  });
  it('keeps stale-offer steps neutral', async () => {
    mount('/client/applications/456', {
      ...checking,
      offer_stale: { reason: 'Source changed' },
    } as typeof checking);
    const track = await screen.findByRole('list', { name: 'Этапы обработки' });
    expect(track.querySelectorAll('.done,.current')).toHaveLength(0);
    expect(screen.getByText('Требуется повторная проверка')).toBeInTheDocument();
  });
  it('does not complete a missing required field merely because all supplied fields are verified', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json({
          ...state,
          applications: [checking],
          requirements: [requirement, { ...requirement, field_code: 'R01_05' }],
        }),
      ),
    );
    const api = new HttpCreditApi();
    await api.refresh();
    const projected = api.getSnapshot().applications[0];
    expect(projected.stage).toBe(-1);
    expect(projected.serverTracks?.client?.states[1]).toBe('unknown');
    expect(projected.history).toEqual([]);
  });
});

describe('HTTP cabinet', () => {
  it('does not overwrite a saved assistant change with an older form', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    const bodies: { expected_version: number; patch: { fields: Record<string, string> } }[] = [];
    let current = { ...application, application_status: 'DRAFT', offer: null };
    const data = () => ({
      ...state,
      applications: [current],
      requirements: [
        {
          product_code: 'R01',
          field_number: 5,
          field_code: 'R01_05',
          field_label: 'Запрашиваемая сумма',
          required_ooo: true,
          required_ip: true,
          target_db_field: 'credit_applications.requested_amount',
          format_rule: null,
        },
      ],
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('action')) {
          const body = JSON.parse(String(init?.body));
          bodies.push(body);
          if (body.expected_version !== current.version)
            return Response.json({ code: 'STALE_CASE_VERSION' }, { status: 409 });
          current = { ...current, version: current.version + 1 };
          return Response.json({ application_id: '456' });
        }
        return Response.json(url.endsWith('session') ? user : data());
      }),
    );
    const api = new HttpCreditApi();
    render(
      <MemoryRouter initialEntries={['/client/new/456']}>
        <Providers api={api}>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    const amount = await screen.findByRole('textbox', { name: 'Запрашиваемая сумма' });
    fireEvent.change(amount, { target: { value: '2500000' } });
    await act(async () => {
      current = { ...current, version: 3, requested_amount: '4000000' };
      await api.refresh();
    });
    expect(amount).toHaveValue('2500000');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await screen.findByText(/Заявка изменилась. Ваш ввод сохранён/);
    expect(bodies[0].expected_version).toBe(2);
    expect(amount).toHaveValue('2500000');
    fireEvent.click(screen.getByRole('button', { name: 'Заменить мой ввод сохранённой версией' }));
    expect(amount).toHaveValue('4000000');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await vi.waitFor(() => expect(bodies).toHaveLength(2));
    expect(bodies[1].expected_version).toBe(3);
    expect(bodies[1].patch.fields.R01_05).toBe('4000000');
  });
  it('requires explicit assistant confirmation and sends only the proposal ID', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    const requests: Record<string, unknown>[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith('action')) {
          requests.push(JSON.parse(String(init?.body)));
          return Response.json({ application_id: '456' });
        }
        return Response.json(
          url.endsWith('session')
            ? user
            : {
                ...state,
                applications: [
                  {
                    ...application,
                    application_status: 'DRAFT',
                    offer: null,
                    dialogue: {
                      history: [{ role: 'assistant', content: 'Проверьте извлечённые сведения.' }],
                      pending: {
                        proposal_id: 'PROP-test',
                        patch: { amount_rub: 1000000 },
                        quotes: { amount_rub: 'миллион рублей' },
                        clear_fields: [],
                      },
                      problems: [],
                    },
                  },
                ],
              },
        );
      }),
    );
    render(
      <MemoryRouter initialEntries={['/client/applications/456']}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    fireEvent.click(await screen.findByRole('button', { name: 'Открыть помощника' }));
    await screen.findByRole('heading', { name: 'Предложенные сведения' });
    expect(requests).toHaveLength(0);
    expect(screen.getByText('Из сообщения: «миллион рублей»')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить предложенные изменения' }));
    await vi.waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0]).toMatchObject({
      action: 'confirm_facts',
      application_id: 456,
      proposal_id: 'PROP-test',
    });
    expect(requests[0]).not.toHaveProperty('patch');
    expect(requests[0]).not.toHaveProperty('company_id');
  });
  it('selecting a file never answers a data request', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    const requests: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (init?.method === 'POST') requests.push(String(init.body));
        return Response.json(
          url.endsWith('session')
            ? user
            : {
                ...state,
                applications: [
                  {
                    ...application,
                    application_status: 'AWAITING_DATA',
                    offer: null,
                    requests: [
                      {
                        request_id: 99,
                        field_code: 'R01_05',
                        question_text: 'Предоставьте выписку',
                        request_status: 'OPEN',
                      },
                    ],
                  },
                ],
              },
        );
      }),
    );
    render(
      <MemoryRouter initialEntries={['/client/applications/456']}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    await screen.findByText('Предоставьте выписку');
    const input = screen.getAllByLabelText('Выбрать PDF или CSV')[1];
    fireEvent.change(input, { target: { files: [new File(['a,b\n1,2'], 'statement.csv')] } });
    expect(requests).toHaveLength(0);
    expect(screen.getByRole('button', { name: 'Отправить ответ' })).toBeDisabled();
    expect(screen.getByText('Предоставьте выписку')).toBeInTheDocument();
  });
  it('filters My reviews by employee ID', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        Response.json(
          url.endsWith('session')
            ? { ...user, role: 'BANK_EMPLOYEE', company_id: null }
            : {
                ...state,
                applications: [
                  {
                    ...application,
                    assignment: { employee_id: 10, first_name: 'Иван', last_name: 'Иванов' },
                  },
                  {
                    ...application,
                    application_id: 457,
                    assignment: { employee_id: 11, first_name: 'Иван', last_name: 'Иванов' },
                  },
                ],
              },
        ),
      ),
    );
    render(
      <MemoryRouter initialEntries={['/bank/mine']}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Мои разборы' });
    expect(screen.getByRole('link', { name: /456/ })).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: /457/ })).not.toBeInTheDocument();
  });
  it('shows stale-offer reason without an acceptance button', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        Response.json(
          url.endsWith('session')
            ? user
            : {
                ...state,
                applications: [
                  {
                    ...application,
                    application_status: 'UNDER_REVIEW',
                    offer: null,
                    offer_stale: {
                      reason: 'Данные изменились, банк повторно проверяет предложение.',
                    },
                  },
                ],
              },
        ),
      ),
    );
    render(
      <MemoryRouter initialEntries={['/client/applications/456']}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    await screen.findByText('Данные изменились, банк повторно проверяет предложение.');
    expect(screen.queryByRole('button', { name: 'Принять предложение' })).not.toBeInTheDocument();
  });
  it('uploads real bytes and reuses a failed upload without answering a request', async () => {
    const bodies: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init: RequestInit) => {
        if (url.endsWith('documents')) {
          bodies.push(String(init.body));
          if (bodies.length === 1)
            return Response.json({ message: 'Upload outage' }, { status: 503 });
          return Response.json({ application_id: '456' });
        }
        return Response.json(state);
      }),
    );
    const api = new HttpCreditApi();
    await api.refresh();
    const file = new File(['a,b\n1,2\n'], 'report.csv', { type: 'text/csv' });
    Object.defineProperty(file, 'arrayBuffer', {
      value: async () => new TextEncoder().encode('a,b\n1,2\n').buffer,
    });
    await expect(api.uploadDocument('456', file, '99')).rejects.toThrow('Upload outage');
    await api.uploadDocument('456', file, '99');
    expect(bodies[0]).toBe(bodies[1]);
    expect(JSON.parse(bodies[0])).toMatchObject({
      action: 'upload',
      data_request_id: 99,
      content_base64: btoa('a,b\n1,2\n'),
    });
    expect(JSON.parse(bodies[0])).not.toHaveProperty('answer');
    await expect(api.uploadDocument('456', new File(['bad'], 'bad.exe'))).rejects.toThrow(
      'PDF и CSV',
    );
  });
  it('takes identity from the server and never stores the password', async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json(user));
    vi.stubGlobal('fetch', fetch);
    const auth = new HttpAuthApi();
    const session = await auth.signIn({
      username: 'client-db',
      password: 'private-test-password',
      role: 'bank',
      firstName: 'Fake',
      lastName: 'Fake',
    });
    expect(session.role).toBe('client');
    expect(session.profile).toBe('123');
    expect(session.firstName).toBe('Иван');
    expect(fetch.mock.calls[0][1].credentials).toBe('same-origin');
    expect(JSON.stringify(localStorage)).not.toContain('private-test-password');
    expect(JSON.stringify(sessionStorage)).not.toContain('private-test-password');
    expect(fetch.mock.calls[0][1].body).not.toContain('Fake');
  });
  it('shows the supplied offer and reason to the client, with no risk, alternatives or demo execution', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => Response.json(url.endsWith('session') ? user : state)),
    );
    render(
      <MemoryRouter initialEntries={['/client/applications/456']}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: 'Предложение банка' });
    expect(screen.getByText('28%')).toBeInTheDocument();
    expect(screen.getByText('Условия проверены сотрудником.')).toBeInTheDocument();
    expect(screen.queryByText(/\bPD\b|Уровень риска|Демо-факторы/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: '18 мес.' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Подписать|Имитировать/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Принять предложение' }));
  });
  it('shows annual PD and its limit only on the bank screen', async () => {
    vi.stubEnv('VITE_API_MODE', 'http');
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        Response.json(
          url.endsWith('session') ? { ...user, role: 'BANK_EMPLOYEE', company_id: null } : state,
        ),
      ),
    );
    render(
      <MemoryRouter initialEntries={['/bank/applications/456']}>
        <Providers>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    await screen.findByText('PD за 12 месяцев');
    expect(screen.getByText('13,18%')).toBeInTheDocument();
    expect(screen.getByText('20%')).toBeInTheDocument();
    expect(screen.queryByText(/Уровень риска|Вклад факторов/)).not.toBeInTheDocument();
  });
  it('reuses the complete mutation after an ambiguous server failure', async () => {
    const crypto = globalThis.crypto;
    vi.stubGlobal('crypto', { getRandomValues: crypto.getRandomValues.bind(crypto) });
    const bodies: string[] = [];
    let failed = false;
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init: RequestInit) => {
        if (url.endsWith('action')) {
          bodies.push(String(init.body));
          if (!failed) {
            failed = true;
            return Response.json({ message: 'Temporary outage' }, { status: 503 });
          }
          return Response.json({ application_id: '456' });
        }
        return Response.json(state);
      }),
    );
    const api = new HttpCreditApi();
    await api.refresh();
    await expect(api.command('score', '456')).rejects.toThrow('Temporary outage');
    await api.command('score', '456');
    expect(bodies[0]).toBe(bodies[1]);
    api.clear();
    expect(api.getSnapshot().applications).toEqual([]);
  });
});
