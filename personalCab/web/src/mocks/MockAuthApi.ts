import { validateSignIn, type AuthApi, type AuthSession, type SignInInput } from '../api/AuthApi';
export const SESSION_KEY = 'aurelius-session';
// Public synthetic credentials for the frontend demo, not secrets or production authentication.
export const demoAccounts: (AuthSession & { label: string; password: string })[] = [
  {
    userId: 'demo-karpov',
    role: 'client',
    profile: 'karpov',
    firstName: 'Илья',
    lastName: 'Карпов',
    username: 'karpov',
    password: 'Aurelius2026!',
    label: 'ИП Карпов',
  },
  {
    userId: 'demo-zerno',
    role: 'client',
    profile: 'zerno',
    firstName: 'Мария',
    lastName: 'Белова',
    username: 'zerno',
    password: 'Aurelius2026!',
    label: 'ООО «Зерно Опт»',
  },
  {
    userId: 'demo-analyst',
    role: 'bank',
    profile: 'karpov',
    firstName: 'Анна',
    lastName: 'Смирнова',
    username: 'analyst',
    password: 'Aurelius2026!',
    label: 'Анна Смирнова',
  },
];
const publicSession = (a: AuthSession): AuthSession => ({
  userId: a.userId,
  role: a.role,
  profile: a.profile,
  firstName: a.firstName,
  lastName: a.lastName,
  username: a.username,
});
export class MockAuthApi implements AuthApi {
  readonly demoAccounts = demoAccounts;
  constructor(private storage: Storage = sessionStorage) {}
  restore = async (): Promise<AuthSession | null> => {
    try {
      const stored = JSON.parse(this.storage.getItem(SESSION_KEY) ?? 'null');
      if (!stored) return null;
      // Restore only public sessions created by the login form; old role-only sessions must sign in again.
      const account = demoAccounts.find(
        (a) =>
          a.userId === stored.userId &&
          a.username === stored.username &&
          a.role === stored.role &&
          a.profile === stored.profile,
      );
      if (
        !account ||
        typeof stored.firstName !== 'string' ||
        !stored.firstName.trim() ||
        typeof stored.lastName !== 'string' ||
        !stored.lastName.trim()
      ) {
        this.storage.removeItem(SESSION_KEY);
        return null;
      }
      return publicSession({ ...account, firstName: stored.firstName, lastName: stored.lastName });
    } catch {
      throw new Error('Не удалось восстановить вход. Разрешите хранилище браузера и повторите.');
    }
  };
  signIn = async (input: SignInInput) => {
    const validation = validateSignIn(input);
    if (Object.keys(validation).length) throw new Error(Object.values(validation)[0]);
    const account = demoAccounts.find(
      (a) =>
        a.role === input.role &&
        a.username === input.username.trim().toLowerCase() &&
        a.password === input.password,
    );
    if (!account) throw new Error('Не удалось войти. Проверьте логин, пароль и выбранный кабинет.');
    const session = publicSession({
      ...account,
      firstName: input.firstName.trim(),
      lastName: input.lastName.trim(),
    });
    try {
      this.storage.setItem(SESSION_KEY, JSON.stringify(session));
    } catch {
      throw new Error('Не удалось сохранить вход. Разрешите хранилище браузера и повторите.');
    }
    return session;
  };
  signOut = async () => {
    try {
      this.storage.removeItem(SESSION_KEY);
    } catch {
      throw new Error('Не удалось завершить вход. Повторите попытку.');
    }
  };
}
