import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { clientVisibleReasons } from '../domain/clientReasons';
import type { ServerApplication, ServerRequirement } from '../domain/types';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const internal = [
  {
    code: 'BANK_CONFIRMATION_REQUIRED',
    message: 'Automatic checks passed; bank employee confirmation required',
  },
  { code: 'PD_LIMIT_EXCEEDED', message: 'PD12 exceeds configured risk appetite' },
  { code: 'DB_INPUTS_UNAVAILABLE', message: 'Internal database input unavailable' },
  { code: 'BANK_APPROVE_EXTRA', message: 'Not an employee approval' },
  { code: 'bank_approve', message: 'Unknown lowercase code' },
];
const employee = ['BANK_APPROVE', 'BANK_REJECT', 'BANK_REQUEST_DATA'].map((code) => ({
  code,
  message: `Причина сотрудника ${code}`,
}));
const sources = ['BANK', 'FNS', 'SME_REGISTER', 'BKI', 'CLIENT', 'CALCULATED', 'OTHER'];
const labels = ['Банк', 'ФНС', 'Реестр МСП', 'БКИ', 'Клиент', 'Расчёт', 'Другое'];
function requirement(n: number, patch: Partial<ServerRequirement> = {}): ServerRequirement {
  return {
    product_code: 'R01',
    field_code: `R01_${String(n).padStart(2, '0')}`,
    field_number: n,
    field_label: `Поле ${n}`,
    required_ooo: true,
    required_ip: true,
    target_db_field: 'application_details.test',
    format_rule: null,
    ...patch,
  };
}
function application(patch: Partial<ServerApplication> = {}): ServerApplication {
  return {
    application_id: 456,
    company_id: 123,
    product_code: 'R01',
    application_status: 'UNDER_REVIEW',
    application_date: '2026-10-26T09:00:00Z',
    requested_amount: '3000000',
    requested_term_months: 36,
    purpose: 'Закупка товаров',
    version: 1,
    form_state: {},
    decision: 'MANUAL_REVIEW',
    offer: null,
    reasons: [],
    assessment: null,
    fields: [],
    requests: [],
    history: [],
    details: null,
    product_details: null,
    ...patch,
  };
}
async function mount(path: string, app = application(), requirements: ServerRequirement[] = []) {
  vi.stubEnv('VITE_API_MODE', 'http');
  const mutations: Record<string, unknown>[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('action')) {
        mutations.push(JSON.parse(String(options?.body)));
        return Response.json({ application_id: '456' });
      }
      return Response.json(
        url.endsWith('session')
          ? {
              user_id: 10,
              login: 'fixture',
              first_name: 'Иван',
              last_name: 'Иванов',
              role: path.startsWith('/bank') ? 'BANK_EMPLOYEE' : 'CLIENT',
              company_id: 123,
            }
          : {
              companies: [
                {
                  company_id: 123,
                  name: 'Компания',
                  inn: '7701000000',
                  entity_type: 'LEGAL_ENTITY',
                  information_reliability_status: 'VERIFIED',
                },
              ],
              applications: [app],
              requirements,
              catalog: [],
            },
      );
    }),
  );
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  await screen.findByRole('heading', {
    name: path.startsWith('/bank')
      ? 'Анкета клиента'
      : path.includes('/new/')
        ? 'Анкета'
        : 'Причины решения',
  });
  return mutations;
}
it('allows only exact employee reason codes and does not mutate the original list', () => {
  const all = [...internal, ...employee];
  const before = structuredClone(all);
  expect(clientVisibleReasons(all)).toEqual(employee);
  expect(all).toEqual(before);
});
it('hides all internal scoring reasons after submission, including BANK_CONFIRMATION_REQUIRED', async () => {
  await mount('/client/applications/456', application({ reasons: internal }));
  const card = screen.getByRole('heading', { name: 'Причины решения' }).parentElement!;
  expect(card).toHaveTextContent('Решение ещё не принято.');
  for (const reason of internal) expect(screen.queryByText(reason.message)).toBeNull();
});
it.each(employee)(
  'shows employee reason $code while filtering mixed scoring reasons',
  async (reason) => {
    await mount('/client/applications/456', application({ reasons: [...internal, reason] }));
    expect(screen.getByText(reason.message)).toBeInTheDocument();
    for (const item of internal) expect(screen.queryByText(item.message)).toBeNull();
  },
);
it('keeps every original English scoring message visible to the employee', async () => {
  await mount('/bank/applications/456', application({ reasons: [...internal, ...employee] }));
  for (const reason of [...internal, ...employee])
    expect(screen.getByText(reason.message)).toBeInTheDocument();
});
it('shows every supported source and all four verification states with semantic colors', async () => {
  const statuses = ['VERIFIED', 'UNVERIFIED', 'CONFLICT', 'EXPIRED', null, 'FUTURE_STATUS', ''];
  const requirements = sources.map((_, i) => requirement(i + 10));
  const fields = sources.map((value_source, i) => ({
    field_code: requirements[i].field_code,
    field_value: `Значение ${i}`,
    value_source,
    verification_status: statuses[i],
  }));
  await mount('/bank/applications/456', application({ fields }), requirements);
  const table = screen.getByRole('table', { name: 'Происхождение данных анкеты' });
  expect(
    within(table)
      .getAllByRole('columnheader')
      .map((c) => c.textContent),
  ).toEqual(['Поле', 'Значение', 'Источник', 'Статус проверки']);
  labels.forEach((label) => expect(within(table).getByText(label)).toBeInTheDocument());
  expect(within(table).getByText('Подтверждено')).toHaveClass('verified');
  expect(within(table).getByText('Не проверено')).toHaveClass('neutral');
  expect(within(table).getByText('Конфликт')).toHaveClass('attention');
  expect(within(table).getByText('Конфликт').closest('tr')).toHaveClass('is-conflict');
  expect(within(table).getByText('Устарело')).toHaveClass('attention');
  expect(within(table).getByText('Неизвестный статус (FUTURE_STATUS)')).toHaveClass('neutral');
  expect(within(table).getAllByText('Нет данных')).toHaveLength(2);
});
it('uses real company values only for absent fields and never invents their provenance or verification', async () => {
  await mount('/bank/applications/456', application(), [
    requirement(3, { field_label: 'ИНН', target_db_field: 'companies.inn' }),
    requirement(5, { target_db_field: 'credit_applications.requested_amount' }),
  ]);
  const table = screen.getByRole('table', { name: 'Происхождение данных анкеты' });
  const inn = within(table).getByRole('rowheader', { name: 'ИНН' }).closest('tr')!;
  expect(inn).toHaveTextContent('7701000000');
  expect(inn).toHaveTextContent('Источник не указан');
  expect(inn).toHaveTextContent('Нет данных');
  expect(inn).not.toHaveTextContent('Подтверждено');
  expect(within(table).getByRole('rowheader', { name: 'Поле 5' }).closest('tr')).toHaveTextContent(
    'Нет данных',
  );
});
it('preserves zero, false and structured values, handles blanks and retains unknown server fields', async () => {
  const values = [null, '', '  ', 0, false, { value: 2 }];
  const fields = values.map((field_value, i) => ({
    field_code: `extra_${i}`,
    field_value,
    value_source: null,
    verification_status: null,
  }));
  await mount('/bank/applications/456', application({ fields }));
  const table = screen.getByRole('table', { name: 'Происхождение данных анкеты' });
  expect(within(table).getByText('0')).toBeInTheDocument();
  expect(within(table).getByText('false')).toBeInTheDocument();
  expect(within(table).getByText('{"value":2}')).toBeInTheDocument();
  values.forEach((_, i) =>
    expect(within(table).getByRole('rowheader', { name: `extra_${i}` })).toBeInTheDocument(),
  );
  expect(within(table).getAllByText('Источник не указан')).toHaveLength(6);
});
it('does not replace an explicitly blank saved field with a company value and keeps unknown source codes honest', async () => {
  await mount(
    '/bank/applications/456',
    application({
      fields: [
        {
          field_code: 'R01_03',
          field_value: '',
          value_source: 'FUTURE_SOURCE',
          verification_status: null,
        },
      ],
    }),
    [requirement(3, { target_db_field: 'companies.inn' })],
  );
  const table = screen.getByRole('table', { name: 'Происхождение данных анкеты' });
  expect(table).not.toHaveTextContent('7701000000');
  expect(table).toHaveTextContent('Источник: FUTURE_SOURCE');
  expect(table).toHaveTextContent('Нет данных');
});
it('shows source badges in the client form without verification statuses', async () => {
  const requirements = sources.map((_, i) => requirement(i + 10));
  const fields = sources.map((value_source, i) => ({
    field_code: requirements[i].field_code,
    field_value: `Значение ${i}`,
    value_source,
    verification_status: 'VERIFIED',
  }));
  await mount(
    '/client/new/456',
    application({ application_status: 'DRAFT', fields }),
    requirements,
  );
  const form = screen.getByRole('heading', { name: 'Анкета' }).closest('form')!;
  labels.forEach((label) =>
    expect(within(form).getByText(label, { selector: '.source' })).toBeInTheDocument(),
  );
  expect(form).not.toHaveTextContent('VERIFIED');
  expect(within(form).queryByText('Подтверждено')).toBeNull();
});
it('labels only actual company prefills as unspecified and preserves the full save payload', async () => {
  const requirements = [
    requirement(3, { field_label: 'ИНН', target_db_field: 'companies.inn' }),
    requirement(5, { target_db_field: 'credit_applications.requested_amount' }),
    requirement(24, { target_db_field: 'companies.missing' }),
  ];
  const mutations = await mount(
    '/client/new/456',
    application({ application_status: 'DRAFT' }),
    requirements,
  );
  const inn = screen.getByLabelText('ИНН');
  expect(inn).toHaveValue('7701000000');
  expect(inn).toHaveAttribute('readonly');
  expect(inn.closest('label')).toHaveTextContent('Источник не указан');
  expect(screen.getByLabelText('Поле 5').closest('label')?.querySelector('.source')).toBeNull();
  expect(screen.getByLabelText('Поле 24').closest('label')?.querySelector('.source')).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
  await waitFor(() => expect(mutations).toHaveLength(1));
  expect(mutations[0]).toMatchObject({
    action: 'save',
    patch: { fields: { R01_03: '7701000000', R01_05: '3000000', R01_24: '' } },
  });
  expect(JSON.stringify(mutations[0])).not.toMatch(/value_source|verification_status/);
});
