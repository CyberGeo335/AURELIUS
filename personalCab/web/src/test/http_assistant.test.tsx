import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { HttpCreditApi } from '../api/HttpCreditApi';
import { HttpV2Api } from '../api/HttpV2Api';
import type { ServerApplication } from '../domain/types';

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

it('allows a slow CPU chat to finish beyond the standard three-minute action timeout', async () => {
  vi.useFakeTimers();
  let finish!: (response: Response) => void;
  let signal!: AbortSignal;
  vi.stubGlobal(
    'fetch',
    vi.fn(
      (_url: string, options: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          finish = resolve;
          signal = options.signal!;
          signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')));
        }),
    ),
  );
  const result = new HttpV2Api().request('action', { kind: 'credit', action: 'chat' });
  await vi.advanceTimersByTimeAsync(240000);
  expect(signal.aborted).toBe(false);
  finish(Response.json({ application_id: '456' }));
  await expect(result).resolves.toMatchObject({ application_id: '456' });
});
function draft(id = 456, patch: Partial<ServerApplication> = {}): ServerApplication {
  return {
    application_id: id,
    company_id: 123,
    product_code: 'R01',
    application_status: 'DRAFT',
    application_date: '2026-10-26T09:00:00Z',
    requested_amount: null,
    requested_term_months: null,
    purpose: null,
    version: 1,
    form_state: {},
    offer: null,
    assessment: null,
    decision: undefined,
    fields: [],
    requests: [],
    history: [],
    reasons: [],
    details: null,
    product_details: null,
    ...patch,
  };
}
const pending = {
  proposal_id: 'PROP-server',
  patch: { amount_rub: 1500000, term_months: 12, purpose: 'INVENTORY' },
  quotes: { amount_rub: 'полтора миллиона', term_months: 'на год', purpose: 'закупка товара' },
  clear_fields: [],
  display_values: { purpose: 'Закупка товаров' },
};
async function mount(path = '/client', initial = [draft()], role: string | null = 'CLIENT') {
  vi.stubEnv('VITE_API_MODE', 'http');
  let apps = initial;
  const commands: Record<string, unknown>[] = [];
  let handler: ((body: Record<string, unknown>) => Promise<Response>) | undefined;
  const api = new HttpCreditApi();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('session'))
        return Response.json(
          role
            ? {
                user_id: 10,
                login: 'client',
                first_name: 'Иван',
                last_name: 'Иванов',
                role,
                company_id: 123,
              }
            : null,
        );
      if (url.endsWith('action')) {
        const body = JSON.parse(String(options?.body));
        commands.push(body);
        if (handler) return handler(body);
        if (body.action === 'create') apps = [...apps, draft(900, { product_code: body.product })];
        if (body.action === 'chat')
          apps = apps.map((a) =>
            a.application_id === body.application_id
              ? {
                  ...a,
                  version: a.version + 1,
                  dialogue: {
                    history: [
                      { role: 'user', content: body.text },
                      { role: 'assistant', content: 'Проверьте сведения из сообщения.' },
                    ],
                    pending,
                    problems: [],
                  },
                }
              : a,
          );
        if (body.action === 'confirm_facts')
          apps = apps.map((a) =>
            a.application_id === body.application_id
              ? {
                  ...a,
                  version: a.version + 1,
                  requested_amount: '1500000',
                  requested_term_months: 12,
                  purpose: 'Закупка товаров',
                  dialogue: {
                    history: [{ role: 'assistant', content: 'Подтверждённые поля сохранены' }],
                    pending: null,
                    problems: [],
                  },
                }
              : a,
          );
        return Response.json({
          application_id: body.action === 'create' ? '900' : String(body.application_id),
        });
      }
      return Response.json({
        companies: [
          { company_id: 123, name: 'Компания', entity_type: 'LEGAL_ENTITY', inn: '7701000000' },
        ],
        applications: apps,
        requirements: [],
        catalog: ['R01', 'R02', 'R03'].map((product_code, i) => ({
          terms_id: i,
          product_code,
          min_amount: '100000',
          max_amount: '5000000',
          min_contract_term_value: 3,
          max_contract_term_value: 36,
          contract_term_unit: 'MONTHS',
        })),
      });
    }),
  );
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers api={api}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  if (role === 'CLIENT') await screen.findByRole('button', { name: 'Открыть чат с помощником' });
  else await screen.findByText(role ? 'Кабинет сотрудника' : 'Войти в кабинет');
  return {
    commands,
    api,
    setApps: (value: ServerApplication[]) => {
      apps = value;
    },
    setHandler: (value: typeof handler) => {
      handler = value;
    },
  };
}
function open() {
  fireEvent.click(screen.getByRole('button', { name: 'Открыть чат с помощником' }));
  return screen.getByRole('dialog', { name: 'Помощник с заявкой' });
}
it('shows an accessible client launcher; Escape returns focus and reopening retains unsent input', async () => {
  await mount();
  const panel = open();
  const input = within(panel).getByLabelText('Расскажите о потребности');
  expect(input).toHaveFocus();
  fireEvent.change(input, { target: { value: 'Моя потребность' } });
  const launcher = screen.getByRole('button', { name: 'Свернуть чат с помощником' });
  expect(launcher).toHaveAttribute('aria-expanded', 'true');
  expect(launcher).toHaveAttribute('aria-controls', panel.id);
  fireEvent.keyDown(window, { key: 'Escape' });
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(launcher).toHaveFocus();
  open();
  expect(within(panel).getByLabelText('Расскажите о потребности')).toHaveValue('Моя потребность');
  expect(localStorage.length).toBe(0);
});
it.each(['BANK_EMPLOYEE', null])('does not show the HTTP assistant for %s', async (role) => {
  await mount(role ? '/bank' : '/', [], role);
  expect(screen.queryByRole('button', { name: 'Открыть чат с помощником' })).toBeNull();
  expect(screen.queryByRole('dialog')).toBeNull();
});
it.each(['/client/applications/456', '/client/new/456'])(
  'prioritizes the owned draft at %s over a newer draft',
  async (path) => {
    await mount(path, [draft(), draft(789, { application_date: '2026-10-26T10:00:00Z' })]);
    expect(open()).toHaveTextContent('Заявка № 456');
  },
);
it('uses the newest own draft outside the draft route and remains open during navigation', async () => {
  await mount('/client', [
    draft(),
    draft(789, { application_date: '2026-10-26T10:00:00Z' }),
    draft(999, { company_id: 999, application_date: '2026-10-27' }),
  ]);
  const panel = open();
  expect(panel).toHaveTextContent('Заявка № 789');
  fireEvent.click(screen.getByRole('link', { name: 'Продукты' }));
  expect(screen.getByRole('dialog')).toBeVisible();
  expect(panel).toHaveTextContent('Заявка № 789');
});
it('always shows the home teaser and creates a draft only on an explicit product button, then sends the saved text', async () => {
  const { commands } = await mount('/client', []);
  fireEvent.click(screen.getByRole('button', { name: /Создать заявку с помощником/ }));
  const panel = screen.getByRole('dialog');
  expect(panel).toHaveTextContent('Новая заявка');
  fireEvent.change(within(panel).getByLabelText('Расскажите о потребности'), {
    target: { value: 'полтора миллиона на год на закупку товара' },
  });
  expect(commands).toHaveLength(0);
  expect(within(panel).getAllByText(/От 100/)).toHaveLength(3);
  fireEvent.click(within(panel).getByRole('button', { name: 'Создать заявку: Кредитная линия' }));
  await within(panel).findByRole('heading', { name: 'Предложенные сведения' });
  expect(commands.map((c) => c.action)).toEqual(['create', 'chat']);
  expect(commands[0]).toMatchObject({ product: 'R02' });
  expect(commands[1]).toMatchObject({
    application_id: 900,
    text: 'полтора миллиона на год на закупку товара',
  });
  expect(panel).toHaveTextContent('Заявка № 900 · Кредитная линия');
});
it('does not change canonical amount, term or purpose on chat and confirms only the server proposal ID', async () => {
  const { commands, api } = await mount('/client/applications/456');
  const panel = open();
  fireEvent.change(within(panel).getByLabelText('Расскажите о потребности'), {
    target: { value: 'полтора миллиона на год на закупку товара' },
  });
  fireEvent.click(within(panel).getByRole('button', { name: 'Отправить сообщение' }));
  await within(panel).findByRole('heading', { name: 'Предложенные сведения' });
  const hero = document.querySelector('.hero')!;
  expect(hero).toHaveTextContent('Сумма не указана');
  expect(hero).toHaveTextContent('Срок не указан');
  expect(hero).toHaveTextContent('Цель: Не указана');
  expect(api.getSnapshot().applications[0].server?.requested_amount).toBeNull();
  expect(within(panel).getByText('Из сообщения: «полтора миллиона»')).toBeInTheDocument();
  expect(commands.map((c) => c.action)).toEqual(['chat']);
  fireEvent.click(
    within(panel).getByRole('button', { name: 'Подтвердить предложенные изменения' }),
  );
  await waitFor(() => expect(hero).toHaveTextContent('1 500 000 ₽'));
  expect(hero).toHaveTextContent('12 мес.');
  expect(hero).toHaveTextContent('Цель: Закупка товаров');
  expect(commands[1]).toMatchObject({
    action: 'confirm_facts',
    application_id: 456,
    proposal_id: 'PROP-server',
  });
  expect(commands[1]).not.toHaveProperty('patch');
  expect(localStorage.length).toBe(0);
});
it('keeps the panel open, blocks repeated sends while waiting, and retains input on extraction 503', async () => {
  const { commands, setHandler } = await mount();
  let finish!: (response: Response) => void;
  setHandler(
    () =>
      new Promise((resolve) => {
        finish = resolve;
      }),
  );
  const panel = open();
  const input = within(panel).getByLabelText('Расскажите о потребности');
  fireEvent.change(input, { target: { value: 'Сохранить этот текст' } });
  const send = within(panel).getByRole('button', { name: 'Отправить сообщение' });
  fireEvent.click(send);
  fireEvent.click(send);
  await within(panel).findByText('Помощник думает, это может занять несколько минут');
  expect(send).toBeDisabled();
  expect(commands).toHaveLength(1);
  await act(async () => {
    finish(
      Response.json(
        { code: 'EXTRACTION_UNAVAILABLE', message: 'Internal extraction error' },
        { status: 503 },
      ),
    );
  });
  expect(
    await within(panel).findByText(
      'Помощник не смог разобрать сообщение — повторите или заполните форму',
    ),
  ).toBeInTheDocument();
  expect(input).toHaveValue('Сохранить этот текст');
  expect(send).toBeEnabled();
  expect(panel).toBeVisible();
});
it('shows company fact labels and quotes without applying the unconfirmed proposal', async () => {
  const { api } = await mount('/client', [draft(456, { dialogue: {
    history: [], problems: [], pending: {
      ...pending,
      patch: { company_name: 'ООО Тест', ogrn: '1990000000032', ogrnip: '399000000000041',
        legal_address: 'г. Москва', director_name: 'Иванов Иван Иванович', okved_main: '46.90',
        registration_date: '2024-05-04', actual_activity_description: 'Оптовая торговля' },
      quotes: { registration_date: 'дата государственной регистрации — 2024-05-04' },
    },
  } })]);
  const panel = open();
  for (const label of ['Полное наименование организации', 'ОГРН', 'ОГРНИП', 'Юридический адрес',
    'ФИО руководителя', 'Основной ОКВЭД', 'Дата государственной регистрации', 'Фактический вид деятельности']) {
    expect(within(panel).getByText(label, { exact: true })).toBeVisible();
  }
  expect(panel).toHaveTextContent('Из сообщения: «дата государственной регистрации — 2024-05-04»');
  expect(api.getSnapshot().applications[0].server?.fields).toEqual([]);
});
it('retries extraction 503 with the same request and clears the error after success', async () => {
  const { commands, setHandler } = await mount();
  setHandler(async () => Response.json({ code: 'EXTRACTION_UNAVAILABLE' }, { status: 503 }));
  const panel = open();
  const input = within(panel).getByLabelText('Расскажите о потребности');
  fireEvent.change(input, { target: { value: 'Миллион на закупку товара' } });
  fireEvent.click(within(panel).getByRole('button', { name: 'Отправить сообщение' }));
  const retry = await within(panel).findByRole('button', { name: 'Повторить сообщение' });
  expect(commands).toHaveLength(1);
  setHandler(async () => Response.json({ application_id: '456' }));
  fireEvent.click(retry);
  await waitFor(() => expect(input).toHaveValue(''));
  expect(commands).toHaveLength(2);
  expect(commands[1]).toEqual(commands[0]);
  expect(within(panel).queryByRole('alert')).toBeNull();
  expect(within(panel).queryByRole('button', { name: 'Повторить сообщение' })).toBeNull();
});
it('opens the same draft form after extraction 503 and preserves the unsent text', async () => {
  const { commands, setHandler } = await mount();
  setHandler(async () => Response.json({ code: 'EXTRACTION_UNAVAILABLE' }, { status: 503 }));
  const panel = open();
  fireEvent.change(within(panel).getByLabelText('Расскажите о потребности'), {
    target: { value: 'Сохранить этот текст' },
  });
  fireEvent.click(within(panel).getByRole('button', { name: 'Отправить сообщение' }));
  const form = await within(panel).findByRole('link', { name: 'Продолжить через форму' });
  expect(form).toHaveAttribute('href', '/client/new/456');
  fireEvent.click(form);
  expect(await screen.findByRole('heading', { name: 'Анкета' })).toBeVisible();
  expect(panel).not.toBeVisible();
  fireEvent.click(screen.getByRole('button', { name: 'Открыть чат с помощником' }));
  expect(within(panel).getByLabelText('Расскажите о потребности')).toHaveValue('Сохранить этот текст');
  expect(commands).toHaveLength(1);
});
it('does not recreate a draft when its initial chat fails after successful creation', async () => {
  const { commands, setHandler, setApps } = await mount('/client', []);
  setHandler(async (body) => {
    if (body.action === 'create') {
      setApps([draft(900)]);
      return Response.json({ application_id: '900' });
    }
    return Response.json({ code: 'EXTRACTION_UNAVAILABLE' }, { status: 503 });
  });
  const panel = open();
  fireEvent.change(within(panel).getByLabelText('Расскажите о потребности'), {
    target: { value: 'Нужны деньги' },
  });
  fireEvent.click(within(panel).getByRole('button', { name: 'Создать заявку: Оборотный кредит' }));
  await within(panel).findByRole('alert');
  expect(panel).toHaveTextContent('Заявка № 900');
  expect(within(panel).getByLabelText('Расскажите о потребности')).toHaveValue('Нужны деньги');
  fireEvent.click(within(panel).getByRole('button', { name: 'Отправить сообщение' }));
  await waitFor(() => expect(commands).toHaveLength(3));
  expect(commands.map((c) => c.action)).toEqual(['create', 'chat', 'chat']);
  expect(commands[1].request_id).toBe(commands[2].request_id);
});
it('switches a bound submitted application to read-only and offers an explicit new application', async () => {
  const { api, setApps, commands } = await mount();
  const panel = open();
  setApps([
    draft(456, {
      application_status: 'UNDER_REVIEW',
      dialogue: {
        history: [{ role: 'user', content: 'Сохранённая история' }],
        pending,
        problems: [],
      },
    }),
  ]);
  await act(async () => api.refresh());
  expect(panel).toHaveTextContent('Сохранённая история');
  expect(panel).toHaveTextContent('только для чтения');
  expect(within(panel).queryByRole('textbox')).toBeNull();
  expect(
    within(panel).queryByRole('button', { name: 'Подтвердить предложенные изменения' }),
  ).toBeNull();
  fireEvent.click(within(panel).getByRole('button', { name: 'Новая заявка с помощником' }));
  expect(panel).toHaveTextContent('Новая заявка');
  expect(commands).toHaveLength(0);
});
it('replaces the embedded composer with a compact action that opens this draft dialogue', async () => {
  await mount('/client/applications/456');
  expect(screen.queryByRole('textbox')).toBeNull();
  fireEvent.click(await screen.findByRole('button', { name: 'Открыть помощника' }));
  expect(screen.getAllByRole('textbox')).toHaveLength(1);
  expect(screen.getByRole('dialog')).toHaveTextContent('Заявка № 456');
});
