import { afterEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { HttpCreditApi } from '../api/HttpCreditApi';
import { clientStatus, httpClientStatus } from '../domain/clientStatus';
import type { ServerApplication } from '../domain/types';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const company = {
  company_id: 123,
  name: 'ООО «Компания из БД»',
  inn: '7701000000',
  entity_type: 'LEGAL_ENTITY',
  okved_main: '46.90',
  registration_date: '2024-06-14',
};
function app(patch: Partial<ServerApplication> = {}): ServerApplication {
  return {
    application_id: 1,
    company_id: 123,
    product_code: 'R01',
    requested_amount: '3000000',
    requested_term_months: 36,
    purpose: 'Пополнение оборотных средств',
    application_status: 'UNDER_REVIEW',
    application_date: '2026-10-26T09:00:00Z',
    version: 1,
    decision: undefined,
    offer: null,
    assessment: null,
    fields: [],
    requests: [],
    history: [],
    reasons: [],
    details: null,
    product_details: null,
    form_state: {},
    ...patch,
  };
}
const offer = (offer_status: 'PROPOSED' | 'ACCEPTED') => ({
  offer_id: 10,
  offer_status,
  offered_amount: '2500000',
  offered_term_months: 36,
  offered_annual_rate_pct: '28',
});
function response(applications: ServerApplication[], companies = [company]) {
  return {
    companies,
    applications,
    requirements: [],
    catalog: [
      {
        product_code: 'R01',
        terms_id: 1,
        min_amount: '100000',
        max_amount: '5000000',
        min_contract_term_value: 3,
        max_contract_term_value: 36,
        contract_term_unit: 'MONTHS',
      },
    ],
  };
}
async function mount(applications: ServerApplication[], companies = [company]) {
  vi.stubEnv('VITE_API_MODE', 'http');
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) =>
      Response.json(
        url.endsWith('session')
          ? {
              user_id: 10,
              login: 'client-db',
              first_name: 'Иван',
              last_name: 'Иванов',
              role: 'CLIENT',
              company_id: 123,
            }
          : response(applications, companies),
      ),
    ),
  );
  render(
    <MemoryRouter initialEntries={['/client']}>
      <Providers>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  await screen.findByRole('heading', { name: 'Ваши заявки' });
  return document.querySelector('.client-home') as HTMLElement;
}
const hero = () => document.querySelector('.client-home .hero') as HTMLElement;

describe('V2 client home with HTTP data', () => {
  it('shows an empty state, company and products without a fictional request or assistant', async () => {
    const home = await mount([]);
    expect(
      within(home).getByRole('heading', { name: 'Дайте бизнесу больше возможностей' }),
    ).toBeInTheDocument();
    expect(within(home).getByRole('link', { name: 'Подать заявку' })).toHaveAttribute(
      'href',
      '/client/products',
    );
    expect(within(home).queryByRole('link', { name: 'Открыть заявку' })).not.toBeInTheDocument();
    expect(within(home).queryByText('Помощник с заявкой')).not.toBeInTheDocument();
    expect(home.querySelector('.stage-track')).toBeNull();
    expect(within(home).getByText('14.06.2024')).toBeInTheDocument();
    expect(within(home).getByText('7701000000')).toBeInTheDocument();
    expect(
      within(home).getByRole('heading', { name: 'Финансирование бизнеса' }),
    ).toBeInTheDocument();
  });
  it('opens a draft form and links its assistant to the detail page', async () => {
    const home = await mount([app({ application_status: 'DRAFT' })]);
    expect(
      within(hero()).getByRole('heading', { name: /Продолжим вашу заявку/ }),
    ).toBeInTheDocument();
    expect(within(hero()).getByRole('link', { name: 'Открыть заявку' })).toHaveAttribute(
      'href',
      '/client/new/1',
    );
    expect(within(home).getByRole('link', { name: /Продолжить с помощником/ })).toHaveAttribute(
      'href',
      '/client/applications/1',
    );
    expect(home.querySelector('.stage-track')).toBeNull();
    expect(
      within(hero()).getByText('Продолжите заполнение, подтвердите сведения и отправьте заявку.'),
    ).toBeInTheDocument();
  });
  it.each([
    [app({ application_status: 'SUBMITTED' }), 'Заявка отправлена', 'Ожидайте проверки.'],
    [app(), 'Проверяем заявку на', 'Ожидайте результата проверки.'],
    [app({ decision: 'MANUAL_REVIEW' }), 'Специалист проверяет', 'Ожидайте решения.'],
    [
      app({ application_status: 'AWAITING_DATA', decision: 'REQUEST_DATA' }),
      'Проверяем заявку на',
      'Откройте заявку и ответьте на запрос банка.',
    ],
    [
      app({ application_status: 'APPROVED', decision: 'APPROVE', offer: offer('PROPOSED') }),
      'Ваше предложение готово',
      'примите предложение либо отклоните его с отменой заявки',
    ],
    [
      app({ application_status: 'APPROVED', decision: 'APPROVE', offer: offer('ACCEPTED') }),
      'Предложение принято',
      'Дополнительных действий в кабинете не требуется.',
    ],
    [
      app({ application_status: 'REJECTED', decision: 'REJECT' }),
      'Решение по заявке',
      'ознакомьтесь с причиной отказа',
    ],
    [
      app({ application_status: 'CANCELLED' }),
      'Заявка отменена',
      'При необходимости создайте новую заявку.',
    ],
    [
      app({ offer_stale: { reason: 'Changed inputs' } }),
      'Проверяем предложение повторно',
      'Ожидайте повторного решения банка.',
    ],
  ])('renders the appropriate title and next step for %#', async (application, title, next) => {
    const home = await mount([application]);
    expect(within(hero()).getByRole('heading', { name: new RegExp(title) })).toBeInTheDocument();
    expect(hero().querySelector('.hero-next')?.textContent).toContain(next);
    expect(within(home).queryByRole('link', { name: 'Что дальше' })).not.toBeInTheDocument();
    expect(home.textContent).not.toMatch(/демо|лизинг|ответьте до|подпишите|внешн.*источник/i);
    expect(within(home).queryByText('Помощник с заявкой')).not.toBeInTheDocument();
  });
  it('uses the latest eligible application, even with newer drafts and closed applications', async () => {
    await mount([
      app({
        application_id: 3,
        application_status: 'DRAFT',
        application_date: '2026-10-26T15:00:00Z',
      }),
      app({
        application_id: 4,
        application_status: 'CANCELLED',
        application_date: '2026-10-26T16:00:00Z',
      }),
      app({ application_id: 2, application_date: '2026-10-26T12:00:00Z' }),
      app({ application_id: 1, application_date: '2026-10-26T09:00:00Z' }),
      app({
        application_id: 5,
        application_status: 'REJECTED',
        application_date: '2026-10-26T17:00:00Z',
      }),
    ]);
    expect(within(hero()).getByText('Заявка № 2')).toBeInTheDocument();
  });
  it('keeps accepted offers eligible and chooses the newest draft for the teaser', async () => {
    const home = await mount([
      app({ application_id: 1, application_status: 'APPROVED', offer: offer('ACCEPTED') }),
      app({
        application_id: 2,
        application_status: 'DRAFT',
        application_date: '2026-10-26T12:00:00Z',
      }),
      app({
        application_id: 3,
        application_status: 'DRAFT',
        application_date: '2026-10-26T11:00:00Z',
      }),
    ]);
    expect(within(hero()).getByText('Заявка № 1')).toBeInTheDocument();
    expect(within(home).getByRole('link', { name: /Продолжить с помощником/ })).toHaveAttribute(
      'href',
      '/client/applications/2',
    );
  });
  it('falls back to the latest application when none are eligible', async () => {
    await mount([
      app({ application_status: 'DRAFT' }),
      app({
        application_id: 2,
        application_status: 'REJECTED',
        application_date: '2026-10-26T12:00:00Z',
      }),
    ]);
    expect(within(hero()).getByText('Заявка № 2')).toBeInTheDocument();
  });
  it('does not display another company applications or open requests', async () => {
    const home = await mount([
      app({
        company_id: 999,
        requests: [
          {
            request_id: 1,
            field_code: 'R01_03',
            question_text: 'Чужой вопрос',
            request_status: 'OPEN',
            answer_value: null,
          },
        ],
      }),
    ]);
    expect(
      within(home).getByRole('heading', { name: 'Дайте бизнесу больше возможностей' }),
    ).toBeInTheDocument();
    expect(home.textContent).not.toContain('Чужой вопрос');
  });
  it.each([null, ''])(
    'does not replace missing amount %j, term or purpose with numbers or a purpose',
    async (requested_amount) => {
      await mount([app({ requested_amount, requested_term_months: null, purpose: '' })]);
      expect(hero().textContent).toContain('Сумма не указана');
      expect(hero().textContent).toContain('Срок не указан');
      expect(hero().textContent).not.toMatch(/0 ₽|0 мес|Цель:/);
    },
  );
  it('shows the earliest open request across applications and counts the others', async () => {
    const request = (
      request_id: number,
      question_text: string,
      requested_at: string,
      request_status = 'OPEN',
    ) => ({
      request_id,
      field_code: 'R01_03',
      question_text,
      requested_at,
      request_status,
      answer_value: null,
    });
    const home = await mount([
      app({
        application_id: 1,
        requests: [
          request(1, 'Новый вопрос', '2026-10-26T12:00:00Z'),
          request(2, 'Закрытый вопрос', '2026-10-20T12:00:00Z', 'ANSWERED'),
        ],
      }),
      app({
        application_id: 2,
        requests: [
          request(3, 'Самый ранний открытый вопрос', '2026-10-24T12:00:00Z'),
          request(4, 'Другой вопрос', '2026-10-25T12:00:00Z'),
        ],
      }),
    ]);
    const card = home.querySelector('.action-card') as HTMLElement;
    expect(
      within(card).getByRole('heading', { name: 'Самый ранний открытый вопрос' }),
    ).toBeInTheDocument();
    expect(within(card).getByText('Ещё 2 запроса')).toBeInTheDocument();
    expect(within(card).getByRole('link', { name: /Ответить банку/ })).toHaveAttribute(
      'href',
      '/client/applications/2',
    );
    expect(card.textContent).not.toMatch(/закрытый вопрос|новый вопрос|лизинг|ответьте до/i);
    expect(card.querySelector('button')).toBeNull();
  });
  it('preserves mock copy while giving HTTP an accepted-offer ending', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        Response.json(
          response([app({ application_status: 'APPROVED', offer: offer('ACCEPTED') })]),
        ),
      ),
    );
    const api = new HttpCreditApi();
    await api.refresh();
    const application = api.getSnapshot().applications[0];
    expect(clientStatus(application).next).toContain('подпишите договор на демо-стенде');
    expect(httpClientStatus(application).next).toBe(
      'Дополнительных действий в кабинете не требуется.',
    );
  });
  it('does not invent company information when it is absent', async () => {
    const home = await mount([], [{ ...company, inn: '', okved_main: '', registration_date: '' }]);
    expect(within(home).getAllByText('Нет данных')).toHaveLength(3);
  });
});
