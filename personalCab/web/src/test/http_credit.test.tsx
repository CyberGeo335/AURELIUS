import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
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

describe('HTTP cabinet', () => {
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
