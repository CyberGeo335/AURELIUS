import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within, cleanup } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { HttpCreditApi } from '../api/HttpCreditApi';
import type { ServerApplication } from '../domain/types';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const actions = [
  'create',
  'save',
  'submit',
  'score',
  'review',
  'verify',
  'accept',
  'cancel',
  'answer',
  'revise',
  'upload',
  'claim',
  'release',
  'chat',
  'confirm_facts',
  'offer_stale',
  'accept_blocked',
  'future_action',
];
const history = actions.map((action, i) => ({
  event_id: i + 1,
  action,
  created_at: `2026-10-26T10:${String(i).padStart(2, '0')}:00Z`,
}));
const offer = {
  offer_id: 25,
  offer_status: 'DRAFT' as const,
  offered_amount: '2500000',
  offered_term_months: 36,
  offered_annual_rate_pct: '28',
};
function application(patch: Partial<ServerApplication> = {}): ServerApplication {
  return {
    application_id: 456,
    company_id: 123,
    product_code: 'R01',
    requested_amount: '3000000',
    requested_term_months: 36,
    purpose: 'Оборотные средства',
    application_status: 'UNDER_REVIEW',
    application_date: '2026-10-26T09:00:00Z',
    version: 2,
    form_state: {},
    decision: 'MANUAL_REVIEW',
    reasons: [],
    offer,
    assessment: null,
    fields: [],
    requests: [],
    history,
    details: null,
    product_details: null,
    assignment: {
      employee_id: 10,
      first_name: 'Иван',
      last_name: 'Иванов',
      assigned_at: '2026-10-26',
    },
    ...patch,
  };
}
function mount(path: string, apps = [application()]) {
  vi.stubEnv('VITE_API_MODE', 'http');
  const fetcher = vi.fn(async (url: string, _options?: RequestInit) =>
    Response.json(
      url.endsWith('session')
        ? {
            user_id: 10,
            login: 'user',
            first_name: 'Иван',
            last_name: 'Иванов',
            role: path.startsWith('/bank') ? 'BANK_EMPLOYEE' : 'CLIENT',
            company_id: 123,
          }
        : {
            companies: [
              { company_id: 123, name: 'Компания', inn: '7701000000', entity_type: 'LEGAL_ENTITY' },
            ],
            applications: apps,
            requirements: [
              {
                product_code: 'R01',
                field_number: 3,
                field_code: 'R01_03',
                field_label: 'ИНН',
                required_ooo: true,
                required_ip: true,
              },
            ],
            catalog: [],
          },
    ),
  );
  vi.stubGlobal('fetch', fetcher);
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  return fetcher;
}
it('shows every bank action, links and current statuses, newest first, without invented audit fields', async () => {
  mount('/bank/journal', [
    application(),
    application({
      application_id: 789,
      application_status: 'REJECTED',
      history: [{ event_id: 90, action: 'review', created_at: '2026-10-27T10:00:00Z' }],
    }),
  ]);
  const table = await screen.findByRole('table');
  expect(
    within(table)
      .getAllByRole('columnheader')
      .map((x) => x.textContent),
  ).toEqual(['Когда', 'Заявка', 'Действие']);
  expect(within(table).getAllByRole('row')[1]).toHaveTextContent('789');
  expect(within(table).getByRole('link', { name: '789' })).toHaveAttribute(
    'href',
    '/bank/applications/789',
  );
  expect(within(table).getAllByRole('row')).toHaveLength(20);
  expect(within(table).getByText('Действие: future_action')).toBeInTheDocument();
  expect(within(table).getByText('Запрошен скоринг')).toBeInTheDocument();
  expect(within(table).getByText('Принятие предложения заблокировано')).toBeInTheDocument();
});
it('shows the application journal in review and an honest empty state', async () => {
  mount('/bank/applications/456', [application({ history: [] })]);
  const heading = await screen.findByRole('heading', { name: 'Журнал заявки' });
  expect(heading.parentElement).toHaveTextContent('Событий пока нет.');
});
it('shows only nine allowed client events without inferring the decision', async () => {
  mount('/client/applications/456');
  const timeline = await screen.findByRole('list', { name: 'История заявки' });
  expect(within(timeline).getAllByRole('listitem')).toHaveLength(9);
  expect(within(timeline).getAllByRole('listitem').at(-1)).toHaveTextContent('Данные изменились');
  expect(within(timeline).getByText('Банк принял решение')).toBeInTheDocument();
  expect(timeline).not.toHaveTextContent(/скоринг|сотрудник|future_action|заблокировано|ассистент/);
  expect(document.querySelector('#history')).toHaveTextContent(
    'Заявку рассматривает специалист банка.',
  );
});
it.each(['APPROVE', 'REJECT', 'REQUEST_DATA'])(
  'previews %s with the same reason and content as the client screen',
  async (decision) => {
    const fetcher = mount('/bank/applications/456');
    await screen.findByRole('heading', { name: 'Решение сотрудника' });
    fireEvent.change(screen.getByLabelText('Решение'), { target: { value: decision } });
    const reason = 'Проверенная причина для клиента';
    fireEvent.change(screen.getByLabelText('Причина, которую увидит клиент'), {
      target: { value: `  ${reason}  ` },
    });
    if (decision === 'REQUEST_DATA')
      fireEvent.change(screen.getByLabelText('Какое поле уточнить'), {
        target: { value: 'R01_03' },
      });
    const preview = screen.getByRole('region', { name: 'Клиент увидит' });
    const previewReasons = within(preview).getByRole('heading', { name: 'Причины решения' })
      .parentElement!.textContent;
    expect(within(preview).queryByRole('button')).toBeNull();
    expect(fetcher.mock.calls.every((call) => !call[1]?.method || call[1].method === 'GET')).toBe(
      true,
    );
    const previewOffer =
      decision === 'APPROVE'
        ? within(preview).getByRole('heading', { name: 'Предложение банка' }).parentElement!
            .textContent
        : null;
    if (decision === 'REJECT') expect(preview).toHaveTextContent('Отказ');
    if (decision === 'REQUEST_DATA') expect(preview).toHaveTextContent('Поле: ИНН');
    cleanup();
    mount('/client/applications/456', [
      application({
        application_status:
          decision === 'APPROVE'
            ? 'APPROVED'
            : decision === 'REJECT'
              ? 'REJECTED'
              : 'AWAITING_DATA',
        decision: decision as ServerApplication['decision'],
        reasons: [{ code: `BANK_${decision}`, message: reason }],
        offer: decision === 'APPROVE' ? { ...offer, offer_status: 'PROPOSED' } : null,
        requests:
          decision === 'REQUEST_DATA'
            ? [
                {
                  request_id: 1,
                  field_code: 'R01_03',
                  question_text: reason,
                  request_status: 'OPEN',
                  answer_value: null,
                },
              ]
            : [],
      }),
    ]);
    const clientReasons = await screen.findByRole('heading', { name: 'Причины решения' });
    expect(clientReasons.parentElement!.textContent).toEqual(previewReasons);
    if (previewOffer)
      expect(
        screen.getByRole('heading', { name: 'Предложение банка' }).parentElement!.textContent,
      ).toEqual(previewOffer);
    if (decision === 'REQUEST_DATA')
      expect(
        screen.getByRole('heading', { name: 'Нужно уточнение' }).parentElement,
      ).toHaveTextContent(`Поле: ИНН`);
  },
);
it('does not invent preview terms or a reason', async () => {
  mount('/bank/applications/456', [application({ offer: null })]);
  const preview = await screen.findByRole('region', { name: 'Клиент увидит' });
  expect(preview).toHaveTextContent('Введите причину для предпросмотра.');
  fireEvent.change(screen.getByLabelText('Причина, которую увидит клиент'), {
    target: { value: 'Причина' },
  });
  expect(preview).toHaveTextContent('Нет рассчитанного предложения.');
  expect(within(preview).queryByText('Предлагаемая сумма')).toBeNull();
});
it('preserves scoring messages for clients as agreed', async () => {
  mount('/client/applications/456', [
    application({
      reasons: [
        { code: 'AUTO', message: 'Automatic checks passed; bank employee confirmation required' },
      ],
    }),
  ]);
  expect(
    await screen.findByText('Automatic checks passed; bank employee confirmation required'),
  ).toBeInTheDocument();
});
it('directs unsupported file names to request documents and still submits text answers', async () => {
  const fetcher = vi.fn(async (_url: string, _options?: RequestInit) =>
    Response.json({ companies: [], applications: [], requirements: [], catalog: [] }),
  );
  vi.stubGlobal('fetch', fetcher);
  const api = new HttpCreditApi();
  await expect(api.answerRequest('456', '1', 'Ответ', 'file.pdf')).rejects.toThrow(
    'Прикрепите файл в блоке «Документы дозапроса»',
  );
  expect(fetcher).not.toHaveBeenCalled();
  await api.answerRequest('456', '1', 'Ответ');
  expect(JSON.parse(fetcher.mock.calls[0][1]!.body as string)).toMatchObject({
    action: 'answer',
    data_request_id: 1,
    answer: 'Ответ',
  });
});
