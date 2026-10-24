import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, afterEach } from 'vitest';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { MockCreditApi, STORAGE_KEY } from '../mocks/MockCreditApi';
import { seedState } from '../mocks/seeds';
const apis: MockCreditApi[] = [];
afterEach(() => apis.forEach((api) => api.destroy()));
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
    expect(screen.getByText('R01-2026-00142 · ревизия 1')).toBeInTheDocument();
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
    await screen.findByRole('heading', { name: 'Помощник сейчас не подключён' });
    expect(screen.getAllByRole('button', { name: 'Новая заявка' })).toHaveLength(3);
  });
  it('guards another borrower’s deep link', async () => {
    open('/client/applications/R01-2026-00151');
    expect(await screen.findByRole('heading', { name: 'Заявка не найдена' })).toBeInTheDocument();
  });
});
