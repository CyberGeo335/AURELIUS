import { useRef, useState } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router';
import {
  ArrowUpRight,
  Building2,
  UserRound,
  Eye,
  EyeOff,
  RotateCcw,
  LockKeyhole,
  Check,
} from 'lucide-react';
import { Action, Card, ErrorState, HeroPanel } from '../../components/v2/primitives';
import { Brand } from '../../components/v2/Brand';
import { Input } from '../../components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
  DialogClose,
} from '../../components/ui/dialog';
import { useAction, useApi, useSession } from '../../app/context';
import { validateSignIn, type SignInInput, type Role } from '../../api/AuthApi';
import { AssistantSessionStore } from '../../api/AssistantSession';
const emptyForm = (role: Role): SignInInput => ({
  role,
  firstName: '',
  lastName: '',
  username: '',
  password: '',
});
export function Login() {
  const auth = useSession();
  const api = useApi();
  const nav = useNavigate();
  const location = useLocation();
  const action = useAction();
  const reset = useAction();
  const [form, setForm] = useState<SignInInput>(() => emptyForm('client'));
  const [errors, setErrors] = useState<ReturnType<typeof validateSignIn>>({});
  const [showPassword, setShowPassword] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const fieldsRef = useRef<HTMLFormElement>(null);
  const change = (field: keyof SignInInput, value: string) => {
    setForm((old) => ({ ...old, [field]: value }));
    setErrors((old) => ({ ...old, [field]: undefined }));
    action.setError('');
  };
  if (auth.loading)
    return (
      <main className="shell">
        <Card>
          <p role="status">Восстанавливаем вход…</p>
        </Card>
      </main>
    );
  const destinationFor = (role: Role) => {
    const destination = location.state?.returnTo;
    const base = `/${role}`;
    return typeof destination === 'string' &&
      (destination === base || destination.startsWith(base + '/'))
      ? destination
      : base;
  };
  if (auth.session) return <Navigate to={destinationFor(auth.session.role)} replace />;
  const submit = () => {
    const validation = validateSignIn(form);
    setErrors(validation);
    if (Object.keys(validation).length) {
      fieldsRef.current
        ?.querySelector<HTMLInputElement>(`[name="${Object.keys(validation)[0]}"]`)
        ?.focus();
      return;
    }
    void action.run(async () => {
      const session = await auth.signIn(form);
      setForm((old) => ({ ...old, password: '' }));
      nav(destinationFor(session.role), { replace: true });
    });
  };
  return (
    <>
      <header className="header">
        <div className="header-inner">
          <Brand />
          <span className="header-note">AURELIUS · демо-стенд</span>
        </div>
      </header>
      <main className="shell auth-page">
        <div className="auth-layout">
          <HeroPanel>
            <p className="hero-eyebrow">Кабинет для бизнеса</p>
            <h1>
              Деньги на планы.
              <br />
              Всё остальное —<br />в кабинете.
            </h1>
            <p className="auth-intro">От первой заявки до решения — понятно, на каждом шаге.</p>
            <div className="auth-benefits">
              <div>
                <Check aria-hidden size={19} />
                <span>Подберите финансирование под свою задачу</span>
              </div>
              <div>
                <Check aria-hidden size={19} />
                <span>Сохраните заявку и вернитесь к ней позже</span>
              </div>
              <div>
                <Check aria-hidden size={19} />
                <span>Получайте запросы и решения в одном месте</span>
              </div>
            </div>
            <div className="auth-demo-note">
              Все данные на стенде синтетические.
              <br />
              Подпись и выдача — имитация.
            </div>
          </HeroPanel>
          <Card className="auth-card">
            <div className="auth-heading">
              <span className="auth-lock">
                <LockKeyhole aria-hidden size={22} />
              </span>
              <div>
                <p className="eyebrow">Добро пожаловать</p>
                <h2>Вход в кабинет</h2>
              </div>
            </div>
            <fieldset className="auth-roles" disabled={action.busy}>
              <legend className="sr-only">Тип кабинета</legend>
              {(
                [
                  ['client', 'Клиент', UserRound],
                  ['bank', 'Сотрудник банка', Building2],
                ] as const
              ).map(([role, label, Icon]) => (
                <label className={`auth-role ${form.role === role ? 'selected' : ''}`} key={role}>
                  <input
                    className="sr-only"
                    type="radio"
                    name="role"
                    value={role}
                    checked={form.role === role}
                    onChange={() => {
                      setForm(emptyForm(role));
                      setErrors({});
                      setShowPassword(false);
                      action.setError('');
                    }}
                  />
                  <Icon aria-hidden size={18} />
                  {label}
                </label>
              ))}
            </fieldset>
            <p className="auth-description muted">
              {form.role === 'client'
                ? 'Заявки, документы и предложения для вашего бизнеса.'
                : 'Очередь заявок, проверка данных и решения по клиентам.'}
            </p>
            <ErrorState message={auth.error} onRetry={() => void auth.restore()} />
            <form
              ref={fieldsRef}
              noValidate
              onSubmit={(e) => {
                e.preventDefault();
                submit();
              }}
            >
              <fieldset disabled={action.busy} className="auth-fields">
                <legend className="sr-only">Данные для входа</legend>
                <div className="auth-names">
                  {(['firstName', 'lastName'] as const).map((field) => (
                    <div className="form-field" key={field}>
                      <label htmlFor={field}>{field === 'firstName' ? 'Имя' : 'Фамилия'}</label>
                      <Input
                        id={field}
                        name={field}
                        value={form[field]}
                        maxLength={60}
                        autoComplete={field === 'firstName' ? 'given-name' : 'family-name'}
                        required
                        aria-invalid={!!errors[field]}
                        aria-describedby={errors[field] ? `${field}-error` : undefined}
                        onChange={(e) => change(field, e.target.value)}
                      />
                      {errors[field] && (
                        <span className="field-error" id={`${field}-error`}>
                          {errors[field]}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
                <div className="form-field">
                  <label htmlFor="username">Логин</label>
                  <Input
                    id="username"
                    name="username"
                    value={form.username}
                    maxLength={80}
                    autoComplete="username"
                    autoCapitalize="none"
                    spellCheck={false}
                    required
                    aria-invalid={!!errors.username}
                    aria-describedby={errors.username ? 'username-error' : undefined}
                    onChange={(e) => change('username', e.target.value)}
                  />
                  {errors.username && (
                    <span className="field-error" id="username-error">
                      {errors.username}
                    </span>
                  )}
                </div>
                <div className="form-field">
                  <label htmlFor="password">Пароль</label>
                  <div className="password-field">
                    <Input
                      id="password"
                      name="password"
                      type={showPassword ? 'text' : 'password'}
                      value={form.password}
                      maxLength={128}
                      autoComplete="current-password"
                      required
                      aria-invalid={!!errors.password}
                      aria-describedby={errors.password ? 'password-error' : undefined}
                      onChange={(e) => change('password', e.target.value)}
                    />
                    <button
                      type="button"
                      className="password-toggle"
                      aria-label={showPassword ? 'Скрыть пароль' : 'Показать пароль'}
                      aria-pressed={showPassword}
                      onClick={() => setShowPassword(!showPassword)}
                    >
                      {showPassword ? (
                        <EyeOff aria-hidden size={19} />
                      ) : (
                        <Eye aria-hidden size={19} />
                      )}
                    </button>
                  </div>
                  {errors.password && (
                    <span className="field-error" id="password-error">
                      {errors.password}
                    </span>
                  )}
                </div>
                <ErrorState message={action.error} />
                <Action type="submit" className="full-width">
                  {action.busy
                    ? 'Входим…'
                    : form.role === 'bank'
                      ? 'Войти сотруднику'
                      : 'Войти в кабинет'}
                  <ArrowUpRight aria-hidden size={18} />
                </Action>
              </fieldset>
            </form>
            {auth.demoAccounts.length > 0 && (
              <details className="auth-demo-access">
                <summary>Демо-доступы</summary>
                <p className="small muted">
                  Выберите профиль, чтобы заполнить поля, затем нажмите «Войти». Пароль для демо:{' '}
                  <code>{auth.demoAccounts.find((a) => a.role === form.role)?.password}</code>
                </p>
                <div className="auth-demo-profiles">
                  {auth.demoAccounts
                    .filter((a) => a.role === form.role)
                    .map((a) => (
                      <button
                        type="button"
                        disabled={action.busy}
                        key={a.userId}
                        onClick={() => {
                          setForm({
                            role: a.role,
                            firstName: a.firstName,
                            lastName: a.lastName,
                            username: a.username,
                            password: a.password,
                          });
                          setErrors({});
                          action.setError('');
                        }}
                      >
                        <UserRound aria-hidden size={17} />
                        <span>
                          {a.label}
                          <span className="block small muted">Логин: {a.username}</span>
                        </span>
                        <ArrowUpRight aria-hidden size={16} />
                      </button>
                    ))}
                </div>
              </details>
            )}
            {auth.demoAccounts.length > 0 && (
              <p className="auth-footnote small muted">
                Демонстрационный вход. Проверка учётных записей пока работает локально, без
                подключения к БД.
              </p>
            )}
          </Card>
        </div>
        <div className="auth-bottom">
          <p className="small muted">AURELIUS · Альфа Будущее · 2026</p>
          <Dialog open={resetOpen} onOpenChange={setResetOpen}>
            <DialogTrigger asChild>
              <Action tone="ghost">
                <RotateCcw aria-hidden size={16} />
                Сбросить демо-данные
              </Action>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Начать демонстрацию заново?</DialogTitle>
                <DialogDescription>
                  Созданные заявки и история демо будут заменены исходными примерами для всех
                  вкладок этого браузера.
                </DialogDescription>
              </DialogHeader>
              <ErrorState message={reset.error} onRetry={reset.retry} />
              <Action
                disabled={reset.busy}
                onClick={() =>
                  reset.run(async () => {
                    await api.reset();
                    new AssistantSessionStore().clear();
                    setResetOpen(false);
                  })
                }
              >
                Сбросить демо-данные
              </Action>
              <DialogClose asChild>
                <Action tone="soft">Сохранить текущие данные</Action>
              </DialogClose>
            </DialogContent>
          </Dialog>
        </div>
      </main>
    </>
  );
}
