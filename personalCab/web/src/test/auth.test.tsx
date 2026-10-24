import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { MockAuthApi, demoAccounts, SESSION_KEY } from '../mocks/MockAuthApi';
import { MockCreditApi } from '../mocks/MockCreditApi';
import { Providers } from '../app/context';
import { App } from '../app/App';
import type { AuthApi } from '../api/AuthApi';
const apis: MockCreditApi[] = [];
afterEach(() => {
  apis.forEach((api) => api.destroy());
  apis.length = 0;
  vi.unstubAllGlobals();
});
async function loginScreen(path = '/', authApi?: AuthApi) {
  const api = new MockCreditApi();
  apis.push(api);
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers api={api} authApi={authApi}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  await screen.findByRole('heading', { name: 'Вход в кабинет' });
}
function fill(username = 'karpov', password = 'Aurelius2026!') {
  fireEvent.change(screen.getByRole('textbox', { name: 'Имя' }), { target: { value: 'Илья' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Фамилия' }), {
    target: { value: 'Карпов' },
  });
  fireEvent.change(screen.getByRole('textbox', { name: 'Логин' }), { target: { value: username } });
  fireEvent.change(screen.getByLabelText('Пароль', { exact: true }), {
    target: { value: password },
  });
}
describe('Frontend authentication adapter', () => {
  it.each(demoAccounts)(
    'signs in $username with the assigned role and never persists the password',
    async (account) => {
      const api = new MockAuthApi();
      const session = await api.signIn(account);
      expect(session.role).toBe(account.role);
      expect(session.profile).toBe(account.profile);
      const stored = sessionStorage.getItem(SESSION_KEY)!;
      expect(stored).not.toContain(account.password);
      expect(stored).not.toContain('password');
      expect(await new MockAuthApi().restore()).toEqual(session);
      await api.signOut();
      expect(await api.restore()).toBeNull();
    },
  );
  it('rejects the wrong password and prevents choosing an employee role with client credentials', async () => {
    const api = new MockAuthApi();
    const account = demoAccounts[0];
    await expect(api.signIn({ ...account, password: 'wrong' })).rejects.toThrow('Проверьте');
    await expect(api.signIn({ ...account, role: 'bank' })).rejects.toThrow('выбранный кабинет');
    expect(await api.restore()).toBeNull();
  });
  it('reports storage failure without creating a session', async () => {
    const storage = {
      getItem: () => null,
      setItem: () => {
        throw new Error('quota');
      },
      removeItem: () => {},
    } as unknown as Storage;
    const api = new MockAuthApi(storage);
    await expect(api.signIn(demoAccounts[0])).rejects.toThrow('Не удалось сохранить вход');
    expect(await api.restore()).toBeNull();
  });
  it('requires sign in for legacy role-only sessions', async () => {
    sessionStorage.setItem(SESSION_KEY, JSON.stringify({ role: 'bank', profile: 'karpov' }));
    expect(await new MockAuthApi().restore()).toBeNull();
  });
});
describe('Login and assistant dock', () => {
  it('validates all four fields and provides an accessible password toggle', async () => {
    await loginScreen();
    fireEvent.click(screen.getByRole('button', { name: 'Войти в кабинет' }));
    expect(screen.getByText('Укажите имя')).toBeInTheDocument();
    expect(screen.getByText('Укажите фамилию')).toBeInTheDocument();
    expect(screen.getByText('Введите логин')).toBeInTheDocument();
    expect(screen.getByText('Введите пароль')).toBeInTheDocument();
    fill();
    fireEvent.click(screen.getByRole('button', { name: 'Показать пароль' }));
    expect(screen.getByLabelText('Пароль', { exact: true })).toHaveAttribute('type', 'text');
    fireEvent.click(screen.getByRole('button', { name: 'Скрыть пароль' }));
    expect(screen.getByLabelText('Пароль', { exact: true })).toHaveAttribute('type', 'password');
  });
  it('retains form data after failed sign in and restores the protected destination after success', async () => {
    await loginScreen('/client/documents');
    fill('karpov', 'wrong');
    fireEvent.click(screen.getByRole('button', { name: 'Войти в кабинет' }));
    await screen.findByText('Не удалось войти. Проверьте логин, пароль и выбранный кабинет.');
    expect(screen.getByRole('textbox', { name: 'Логин' })).toHaveValue('karpov');
    expect(screen.getByLabelText('Пароль', { exact: true })).toHaveValue('wrong');
    fireEvent.change(screen.getByLabelText('Пароль', { exact: true }), {
      target: { value: 'Aurelius2026!' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Войти в кабинет' }));
    await screen.findByRole('heading', { name: 'Документы и согласия' });
    expect(screen.getByText('Илья Карпов')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Выйти из кабинета' }));
    await screen.findByRole('heading', { name: 'Вход в кабинет' });
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
    expect(screen.getByLabelText('Пароль', { exact: true })).toHaveValue('');
  });
  it('signs an employee into the bank workspace without a client chat', async () => {
    await loginScreen();
    fireEvent.click(screen.getByRole('radio', { name: 'Сотрудник банка' }));
    fireEvent.click(screen.getByText('Демо-доступы'));
    fireEvent.click(screen.getByRole('button', { name: /Анна Смирнова.*analyst/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Войти сотруднику' }));
    await screen.findByRole('heading', { name: 'Очередь' });
    expect(screen.getByText('Анна Смирнова')).toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'Открыть чат с помощником' }),
    ).not.toBeInTheDocument();
  });
  it('keeps the compact chat and unfinished message when minimized and when navigating', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('{}', { status: 503 })));
    await loginScreen();
    fill();
    fireEvent.click(screen.getByRole('button', { name: 'Войти в кабинет' }));
    const launcher = await screen.findByRole('button', { name: 'Открыть чат с помощником' });
    fireEvent.click(launcher);
    const panel = await screen.findByRole('dialog');
    expect(panel).toHaveAttribute('id', 'assistant-chat');
    expect(launcher).toHaveAttribute('aria-expanded', 'true');
    fireEvent.change(screen.getByRole('textbox', { name: 'Ваше сообщение' }), {
      target: { value: 'Хочу уточнить условия' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Свернуть чат с помощником' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'Открыть чат с помощником' }));
    expect(await screen.findByRole('textbox', { name: 'Ваше сообщение' })).toHaveValue(
      'Хочу уточнить условия',
    );
    fireEvent.click(screen.getByRole('link', { name: 'Компания' }));
    await screen.findByRole('heading', { name: 'Компания' });
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
  it('restores access through an injected authentication adapter', async () => {
    const account = demoAccounts[1];
    const auth: AuthApi = {
      restore: vi.fn().mockResolvedValue(account),
      signIn: vi.fn(),
      signOut: vi.fn().mockResolvedValue(undefined),
    };
    const api = new MockCreditApi();
    apis.push(api);
    render(
      <MemoryRouter initialEntries={['/bank']}>
        <Providers api={api} authApi={auth}>
          <App />
        </Providers>
      </MemoryRouter>,
    );
    await screen.findByRole('heading', { name: /Специалист проверяет/ });
    expect(screen.queryByRole('heading', { name: 'Очередь' })).not.toBeInTheDocument();
    expect(screen.getByText('Мария Белова')).toBeInTheDocument();
  });
});
