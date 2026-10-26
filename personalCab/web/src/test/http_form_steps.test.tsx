import { afterEach, expect, it, vi } from 'vitest';
import { act, fireEvent, screen, within, waitFor } from '@testing-library/react';
import { application, requirements, mountQueueForm } from './queueFormFixtures';
import { initialFields, fieldStep, formStepTitles } from '../domain/formSteps';
import type { Product } from '../domain/types';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});
const steps = () => screen.getByRole('complementary', { name: 'Шаги анкеты' });
const summary = () => screen.getByRole('complementary', { name: 'Сводка заявки' });
const stepButton = (index: number) =>
  within(steps()).getByRole('button', { name: new RegExp(formStepTitles[index]) });
const currentStep = (index: number) =>
  expect(stepButton(index)).toHaveAttribute('aria-current', 'step');

it('restores a saved step and persists forward full saves and backward step-only navigation', async () => {
  const app = application(1, {
    form_state: { step: 2, businessConfirmed: true, consentData: true, consentBki: true },
  });
  const { commands } = await mountQueueForm('/client/new/1', [app]);
  currentStep(2);
  expect(screen.getByLabelText('Поле 24')).toBeVisible();
  expect(screen.getByLabelText('Поле 5')).not.toBeVisible();
  fireEvent.click(stepButton(0));
  await waitFor(() => currentStep(0));
  expect(commands[0]).toMatchObject({ action: 'save', patch: { step: 0 } });
  expect(commands[0].patch as object).not.toHaveProperty('fields');
  fireEvent.change(screen.getByLabelText('Поле 5'), { target: { value: '2500000' } });
  fireEvent.click(screen.getByRole('button', { name: 'Дальше: Реквизиты бизнеса' }));
  await waitFor(() => currentStep(1));
  expect(commands[1]).toMatchObject({
    action: 'save',
    expected_version: 2,
    patch: { step: 1, amount: '2500000', fields: { R01_05: '2500000', R01_24: 'Значение 24' } },
  });
  expect(screen.getByLabelText('Поле 3')).toBeVisible();
  expect(screen.getByLabelText('Поле 5')).not.toBeVisible();
});
it('blocks forward navigation and submission while required values are missing', async () => {
  const app = application();
  app.fields = app.fields.filter((f) => f.field_code !== 'R01_05');
  app.requested_amount = null;
  const { commands } = await mountQueueForm('/client/new/1', [app]);
  expect(screen.getByRole('button', { name: 'Дальше: Реквизиты бизнеса' })).toBeDisabled();
  expect(stepButton(4)).toBeDisabled();
  expect(screen.queryByRole('button', { name: 'Отправить заявку' })).toBeNull();
  expect(summary()).toHaveTextContent('Сумма не указана');
  expect(summary()).not.toHaveTextContent('0 ₽');
  fireEvent.submit(screen.getByRole('heading', { name: 'Анкета' }).closest('form')!);
  expect(commands).toHaveLength(0);
  fireEvent.change(screen.getByLabelText('Поле 5'), { target: { value: '1500000' } });
  expect(screen.getByRole('button', { name: 'Дальше: Реквизиты бизнеса' })).toBeEnabled();
});
it.each(['R01', 'R02', 'R03'] as Product[])(
  'calculates readiness for both applicant types from real %s requirement flags',
  async (product) => {
    const definitions = requirements(product);
    expect(definitions.filter((r) => r.required_ip)).toHaveLength(product === 'R01' ? 24 : 27);
    expect(definitions.filter((r) => r.required_ooo)).toHaveLength(product === 'R01' ? 29 : 32);
  },
);
it.each([
  ['R01', 'INDIVIDUAL_ENTREPRENEUR', 27],
  ['R01', 'LEGAL_ENTITY', 32],
  ['R02', 'INDIVIDUAL_ENTREPRENEUR', 32],
  ['R02', 'LEGAL_ENTITY', 37],
  ['R03', 'INDIVIDUAL_ENTREPRENEUR', 32],
  ['R03', 'LEGAL_ENTITY', 37],
] as const)(
  'shows correct %s %s readiness including agreements and tranche controls',
  async (product, entity, total) => {
    const app = application(1, { product_code: product });
    app.fields = app.fields.filter((f) => f.field_code !== `${product}_05`);
    app.requested_amount = null;
    await mountQueueForm('/client/new/1', [app], requirements(product), entity);
    expect(screen.getByRole('progressbar', { name: 'Готовность заявки' })).toHaveAttribute(
      'value',
      String(Math.round(((total - 1) / total) * 100)),
    );
    expect(summary()).toHaveTextContent('Поле 5');
    expect(summary()).not.toHaveTextContent(/платёж|ставка|% годовых/i);
  },
);
it('does not require legal-entity-only fields from an individual entrepreneur', async () => {
  const app = application();
  app.fields = app.fields.filter((f) => f.field_code !== 'R01_09');
  await mountQueueForm('/client/new/1', [app], requirements(), 'INDIVIDUAL_ENTREPRENEUR');
  expect(screen.getByRole('progressbar')).toHaveAttribute('value', '100');
  expect(screen.queryByLabelText('Поле 9')).toBeNull();
});
it.each(['R02', 'R03'] as Product[])(
  'retains separate %s tranche values and units without converting days or changing field persistence',
  async (product) => {
    const app = application(1, { product_code: product, product_details: null });
    const { commands } = await mountQueueForm('/client/new/1', [app], requirements(product));
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '95');
    expect(stepButton(1)).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Срок транша'), { target: { value: '10' } });
    fireEvent.change(screen.getByLabelText('Единица срока транша'), {
      target: { value: 'MONTHS' },
    });
    expect(screen.getByRole('progressbar')).toHaveAttribute('value', '100');
    fireEvent.click(screen.getByRole('button', { name: 'Дальше: Реквизиты бизнеса' }));
    await waitFor(() => currentStep(1));
    expect(commands[0]).toMatchObject({
      patch: {
        step: 1,
        product_details: { max_tranche_term_value: 10, max_tranche_term_unit: 'MONTHS' },
      },
    });
    expect((commands[0].patch as { fields: Record<string, string> }).fields[`${product}_32`]).toBe(
      product === 'R03' ? '40702810000000000001' : '30',
    );
    expect((commands[0].patch as { product_details: object }).product_details).not.toHaveProperty(
      'max_tranche_term_days',
    );
  },
);
it('groups product-specific requirements without adding an income-entry step', () => {
  expect(fieldStep(requirements('R02')[31], 'R02')).toBe(0);
  expect(fieldStep(requirements('R03')[31], 'R03')).toBe(1);
  expect(fieldStep(requirements()[30], 'R01')).toBe(3);
  expect(fieldStep(requirements()[23], 'R01')).toBe(2);
  expect(formStepTitles.join(' ')).not.toMatch(/оборот|выручк/i);
});
it('keeps the existing positive whole-number requirement for tranche input', async () => {
  await mountQueueForm(
    '/client/new/1',
    [application(1, { product_code: 'R02' })],
    requirements('R02'),
  );
  fireEvent.change(screen.getByLabelText('Срок транша'), { target: { value: '-1' } });
  expect(stepButton(1)).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Срок транша'), { target: { value: '1.5' } });
  expect(stepButton(1)).toBeDisabled();
});
it('requires all three agreements and the application confirmation before the last step', async () => {
  const app = application(1, {
    form_state: { step: 3, businessConfirmed: false, consentData: false, consentBki: false },
  });
  app.fields = app.fields.map((f) => (f.field_code === 'R01_31' ? { ...f, field_value: '' } : f));
  await mountQueueForm('/client/new/1', [app]);
  currentStep(3);
  expect(stepButton(4)).toBeDisabled();
  expect(screen.getByRole('progressbar')).toHaveAttribute('value', '88');
  for (const checkbox of screen.getAllByRole('checkbox')) fireEvent.click(checkbox);
  expect(stepButton(4)).toBeEnabled();
  expect(screen.getByRole('progressbar')).toHaveAttribute('value', '100');
});
it('submits only from the last step and displays the backend validation error verbatim', async () => {
  const app = application(1, {
    form_state: { step: 4, businessConfirmed: true, consentData: true, consentBki: true },
  });
  const { commands, setHandler } = await mountQueueForm('/client/new/1', [app]);
  currentStep(4);
  setHandler((body) =>
    body.action === 'submit'
      ? Response.json({ message: 'Заполните обязательные поля: Проверка сервера' }, { status: 400 })
      : undefined,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Отправить заявку' }));
  await screen.findByText('Заполните обязательные поля: Проверка сервера');
  expect(commands.map((c) => c.action)).toEqual(['save', 'submit']);
});
it('disables the final submission button and lists gaps after adopting an incomplete external update', async () => {
  const app = application(1, {
    form_state: { step: 4, businessConfirmed: true, consentData: true, consentBki: true },
  });
  const { api, setApps } = await mountQueueForm('/client/new/1', [app]);
  setApps([
    {
      ...app,
      version: 2,
      requested_amount: null,
      fields: app.fields.filter((f) => f.field_code !== 'R01_05'),
    },
  ]);
  await act(async () => api.refresh());
  fireEvent.click(
    await screen.findByRole('button', { name: 'Заменить мой ввод сохранённой версией' }),
  );
  expect(screen.getByRole('button', { name: 'Отправить заявку' })).toBeDisabled();
  expect(screen.getByText('Осталось заполнить', { exact: true })).toBeInTheDocument();
});
it.each([0, 1, 2, 3, 4])(
  'updates confirmed assistant values on step %i and leaves chat-only proposals unapplied',
  async (step) => {
    const app = application(1, {
      form_state: { step, businessConfirmed: true, consentData: true, consentBki: true },
    });
    const { api, setApps, commands } = await mountQueueForm('/client/new/1', [app]);
    currentStep(step);
    const chat = {
      ...app,
      version: 2,
      history: [{ event_id: 1, action: 'chat', created_at: '2026-10-26T10:00:00Z' }],
    };
    setApps([chat]);
    await act(async () => api.refresh());
    expect(screen.getByLabelText('Поле 5')).toHaveValue('3000000');
    const confirmed = {
      ...chat,
      version: 3,
      requested_amount: '4000000',
      fields: app.fields.map((f) =>
        f.field_code === 'R01_05' ? { ...f, field_value: '4000000' } : f,
      ),
      history: [
        ...chat.history,
        { event_id: 2, action: 'confirm_facts', created_at: '2026-10-26T10:01:00Z' },
      ],
    };
    setApps([confirmed]);
    await act(async () => api.refresh());
    await waitFor(() => expect(screen.getByLabelText('Поле 5')).toHaveValue('4000000'));
    currentStep(step);
    expect(summary()).toHaveTextContent('4 000 000 ₽');
    fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
    await waitFor(() => expect(commands).toHaveLength(1));
    expect(commands[0]).toMatchObject({
      expected_version: 3,
      patch: { step, fields: { R01_05: '4000000' } },
    });
  },
);
it('preserves unrelated unsaved contact edits when assistant confirmation changes the amount', async () => {
  const app = application(1, {
    form_state: { step: 2, businessConfirmed: true, consentData: true, consentBki: true },
  });
  const { api, setApps, commands } = await mountQueueForm('/client/new/1', [app]);
  fireEvent.change(screen.getByLabelText('Поле 24'), { target: { value: 'Моя правка контакта' } });
  setApps([
    {
      ...app,
      version: 2,
      requested_amount: '4000000',
      fields: app.fields.map((f) =>
        f.field_code === 'R01_05' ? { ...f, field_value: '4000000' } : f,
      ),
      history: [{ event_id: 1, action: 'confirm_facts', created_at: '2026-10-26T10:00:00Z' }],
    },
  ]);
  await act(async () => api.refresh());
  expect(screen.getByLabelText('Поле 24')).toHaveValue('Моя правка контакта');
  expect(summary()).toHaveTextContent('4 000 000 ₽');
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить черновик' }));
  await waitFor(() => expect(commands).toHaveLength(1));
  expect(commands[0]).toMatchObject({
    patch: { fields: { R01_24: 'Моя правка контакта', R01_05: '4000000' } },
  });
});

it.each(['R01', 'R02', 'R03'] as Product[])(
  'prefills only the %s OKVED code when the company also has its name',
  (product) => {
    const rows = requirements(product).map((r) =>
      r.field_number === 17
        ? {
            ...r,
            target_db_field: 'companies.okved_main + companies.okved_main_name',
          }
        : r,
    );
    const app = { product, fields: {} } as Parameters<typeof initialFields>[1];
    const company = {
      id: '1',
      entity: 'OOO',
      name: 'Fixture',
      inn: '',
      registration: '',
      registered: '',
      okved: '46.90',
      flow: 0,
      existing: 0,
      monthly: [],
      server: { okved_main: '46.90', okved_main_name: 'Оптовая торговля' },
    } as Parameters<typeof initialFields>[2];
    expect(initialFields(rows, app, company)[`${product}_17`]).toBe('46.90');
    company.server = { okved_main: null, okved_main_name: 'Оптовая торговля' };
    expect(initialFields(rows, app, company)[`${product}_17`]).toBe('');
  },
);
