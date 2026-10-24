import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, afterEach, vi } from 'vitest';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { MockCreditApi, STORAGE_KEY } from '../mocks/MockCreditApi';
import { seedState } from '../mocks/seeds';
const apis: MockCreditApi[] = [];
afterEach(() => {
  apis.forEach((api) => api.destroy());
  vi.unstubAllGlobals();
});
function open(path: string, role: 'client' | 'bank' = 'client') {
  sessionStorage.setItem('aurelius-session', JSON.stringify({ role, profile: 'karpov' }));
  const api = new MockCreditApi();
  apis.push(api);
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers api={api}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  return api;
}
describe('Key screens', () => {
  it('shows an older open request when the hero displays a newer offer', async () => {
    const state = seedState();
    const newer = structuredClone(state.applications.find((a) => a.companyId === 'potok')!);
    newer.id = 'R01-2026-00999';
    newer.companyId = 'karpov';
    state.applications.unshift(newer);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    open('/client');
    expect(screen.getByRole('heading', { name: /Ваше предложение готово/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Ответить банку' }));
    expect(
      await screen.findByRole('heading', { name: 'Нужно ваше уточнение' }),
    ).toBeInTheDocument();
    expect(screen.getByText('R01-2026-00142')).toBeInTheDocument();
  });
  it('renders the client home with active request and products', () => {
    open('/client');
    expect(screen.getByRole('heading', { name: /Проверяем заявку/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Ответить банку' })).toBeEnabled();
    expect(screen.getAllByRole('button', { name: 'Новая заявка' })).toHaveLength(3);
  });
  it('filters the bank queue without losing the application link', async () => {
    open('/bank', 'bank');
    fireEvent.click(await screen.findByRole('button', { name: /Ждут клиента/ }));
    expect(screen.getByText('R03-2026-00007')).toBeInTheDocument();
    expect(screen.queryByText('R01-2026-00151')).not.toBeInTheDocument();
  });
  it('requires a justification and writes a counteroffer visible to the client', async () => {
    const api = open('/bank/applications/R01-2026-00151', 'bank');
    const button = await screen.findByRole('button', { name: 'Сохранить решение' });
    expect(button).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Обоснование — обязательно' }), {
      target: { value: 'Расхождение объяснено, вариант А покрывается потоком.' },
    });
    expect(button).toBeDisabled();
    expect(screen.getByRole('radio', { name: /Предложить вариант А/ })).toBeDisabled();
    fireEvent.change(screen.getByRole('textbox', { name: 'Комментарий к проверке' }), {
      target: { value: 'Доверенность и данные источника проверены в демо.' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить полномочия' }));
    await waitFor(() =>
      expect(
        api.getSnapshot().applications.find((a) => a.id === 'R01-2026-00151')?.checks?.authority,
      ).toBe(true),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить источник' }));
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() =>
      expect(api.getSnapshot().applications.find((a) => a.id === 'R01-2026-00151')?.status).toBe(
        'OFFERED',
      ),
    );
    expect(
      screen.getByText('Состояние заявки обновлено. Решение уже доступно в кабинете клиента.'),
    ).toBeInTheDocument();
  });
  it('keeps assistant failure separate from the main form', async () => {
    open('/client');
    fireEvent.click(screen.getByRole('button', { name: 'Спросить о заявке' }));
    await screen.findByRole('heading', { name: 'Продолжим через форму' });
    expect(screen.getAllByRole('button', { name: 'Новая заявка' })).toHaveLength(3);
  });
  it('guards another borrower’s deep link', async () => {
    open('/client/applications/R01-2026-00151');
    expect(await screen.findByRole('heading', { name: 'Нет доступа' })).toBeInTheDocument();
  });
  it('shows consent details in a dedicated document layout', async () => {
    open('/client/documents');
    expect(screen.getByRole('heading', { name: 'Документы и согласия' })).toBeInTheDocument();
    expect(screen.getAllByText('Файлов пока нет')).toHaveLength(2);
    fireEvent.click(screen.getAllByRole('button', { name: 'Подробнее: кредитная история' })[0]);
    expect(await screen.findByRole('dialog')).toHaveTextContent('bki-demo-2026.10-v1');
  });
  it('keeps internal bank audit out of the client application', async () => {
    open('/client/applications/R01-2026-00142');
    await screen.findByRole('heading', { name: 'Нужно ваше уточнение' });
    expect(
      screen.queryByText(/score-model|policy-2026|FS-R01|Журнал действий банка/),
    ).not.toBeInTheDocument();
    const disclosure = screen.getByRole('button', { name: /Документы и согласия/ });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    fireEvent.click(disclosure);
    expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByRole('heading', { name: 'Согласия' })).toBeVisible();
  });
  it('selects a product by need and calculates before creating the draft', async () => {
    const api = open('/client/products');
    expect(screen.getByText(/≈ 142/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Закупки каждый месяц' }));
    fireEvent.click(screen.getByRole('button', { name: 'Оформить заявку' }));
    await screen.findByRole('heading', { name: 'На что нужны деньги?' });
    expect(api.getSnapshot().applications.find((a) => a.status === 'DRAFT')?.product).toBe('R02');
  });
  it('previews a new term without changing the offer until recheck', async () => {
    const state = seedState();
    const offer = state.applications.find((a) => a.companyId === 'potok')!;
    offer.companyId = 'karpov';
    offer.amount = 1500000;
    offer.term = 12;
    offer.offers[0].amount = 1500000;
    offer.offers[0].term = 12;
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    const api = open('/client/applications/' + offer.id);
    fireEvent.click(await screen.findByRole('button', { name: '18 мес.' }));
    expect(api.getSnapshot().applications.find((a) => a.id === offer.id)?.revision).toBe(1);
    expect(screen.getByRole('button', { name: 'Перепроверить на 18 мес.' })).toBeEnabled();
    expect(screen.queryByRole('button', { name: 'Принять предложение' })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Перепроверить на 18 мес.' }));
    await waitFor(() =>
      expect(api.getSnapshot().applications.find((a) => a.id === offer.id)?.status).toBe(
        'CHECKING',
      ),
    );
  });
  it('confirms actual chat candidates into one shared draft without granting consent', async () => {
    const response = {
      result: {
        case_id: 'case-test',
        message: 'Проверьте сумму и срок.',
        request: { legal_form: 'IP', amount_rub: 1500000, term_months: 12, purpose: 'INVENTORY' },
        product_selection: {
          candidates: [
            {
              product_id: 'rcl',
              product_family: 'REVOLVING_CREDIT_LINE',
              name: 'Кредитная линия',
              eligibility: 'MATCH',
              priority: 1,
              reasons: ['Для регулярных закупок'],
              missing_checks: [],
              requirements: [],
            },
          ],
        },
      },
    };
    vi.stubGlobal(
      'fetch',
      vi.fn(
        async (path: string) =>
          new Response(
            JSON.stringify(
              path === '/api/health'
                ? { status: 'ready' }
                : path === '/api/chat/state'
                  ? { history: [], latest: null }
                  : response,
            ),
            { status: 200 },
          ),
      ),
    );
    const api = open('/client/products');
    fireEvent.click(screen.getByRole('button', { name: 'Подобрать с помощником' }));
    await screen.findByText('Ассистент доступен');
    fireEvent.change(screen.getByRole('textbox', { name: 'Ваше сообщение' }), {
      target: { value: 'Нужны полтора миллиона на товар на год' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await screen.findByText('Для регулярных закупок');
    expect(
      api.getSnapshot().applications.filter((a) => a.status === 'DRAFT' && a.product === 'R02'),
    ).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', { name: 'Да, верно' }));
    await screen.findByRole('button', { name: 'Перейти к анкете' });
    const draft = api
      .getSnapshot()
      .applications.find((a) => a.status === 'DRAFT' && a.product === 'R02')!;
    expect(draft.product).toBe('R02');
    expect(draft.consentBki).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Поправить' }));
    fireEvent.change(
      within(screen.getByRole('dialog')).getByRole('spinbutton', { name: 'Сумма, ₽' }),
      { target: { value: '1800000' } },
    );
    fireEvent.click(screen.getByRole('button', { name: 'Да, верно' }));
    await waitFor(() =>
      expect(api.getSnapshot().applications.find((a) => a.id === draft.id)?.revision).toBe(2),
    );
    expect(
      api.getSnapshot().applications.filter((a) => a.status === 'DRAFT' && a.product === 'R02'),
    ).toHaveLength(1);
  });
  it('shows the initial October 18 draft with a resume action', () => {
    open('/client/applications');
    expect(screen.getByText(/R01-2026-00140.*18.10/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Продолжить' })).toHaveAttribute(
      'href',
      '/client/new/R01-2026-00140',
    );
  });
  it('renders stale source metadata explicitly in the bank dossier', async () => {
    const state = seedState();
    const app = state.applications.find((a) => a.id === 'R01-2026-00151')!;
    app.fieldStatuses = { R01_09: 'STALE' };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    open('/bank/applications/' + app.id, 'bank');
    expect(await screen.findByText('Устарело')).toBeInTheDocument();
  });

  it('retries a failed assistant request with the persisted message identifier', async () => {
    const bodies: string[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (path: string, init?: RequestInit) => {
        if (path === '/api/health') return new Response(JSON.stringify({ status: 'ready' }));
        if (path === '/api/chat/state')
          return new Response(JSON.stringify({ history: [], latest: null }));
        bodies.push(String(init?.body));
        return bodies.length === 1
          ? new Response('{}', { status: 503 })
          : new Response(JSON.stringify({ result: { message: 'Уточните срок.' } }));
      }),
    );
    open('/client/products');
    fireEvent.click(screen.getByRole('button', { name: 'Подобрать с помощником' }));
    await screen.findByText('Ассистент доступен');
    fireEvent.change(screen.getByRole('textbox', { name: 'Ваше сообщение' }), {
      target: { value: 'Нужен кредит на товар' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
    await screen.findByRole('button', { name: 'Повторить запрос' });
    fireEvent.click(screen.getByRole('button', { name: /^Повторить$/ }));
    await screen.findByText('Уточните срок.');
    expect(bodies).toHaveLength(2);
    expect(bodies[1]).toBe(bodies[0]);
    expect(screen.getAllByText('Нужен кредит на товар')).toHaveLength(1);
  });
});
