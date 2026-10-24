import {
  Component,
  lazy,
  Suspense,
  useEffect,
  useState,
  type ErrorInfo,
  type ReactNode,
} from 'react';
import {
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
} from 'react-router';
import { LogOut, MessageCircle, ChevronDown } from 'lucide-react';
import { useAction, useCredit, useSession } from './context';
import { Action, Card, CompanyCard, EmptyState, ErrorState } from '../components/v2/primitives';
import { Brand } from '../components/v2/Brand';
import { Login } from '../pages/auth/Login';
import { AssistantPanel } from '../components/v2/AssistantPanel';
import { Home, Applications } from '../pages/client/Home';
import { Products } from '../pages/client/Products';
import { Documents } from '../pages/client/Documents';
const ApplicationForm = lazy(() =>
  import('../pages/client/ApplicationForm').then((m) => ({ default: m.ApplicationForm })),
);
const ApplicationDetail = lazy(() =>
  import('../pages/client/ApplicationDetail').then((m) => ({ default: m.ApplicationDetail })),
);
const Queue = lazy(() => import('../pages/bank/Queue').then((m) => ({ default: m.Queue })));
const BankJournal = lazy(() =>
  import('../pages/bank/Queue').then((m) => ({ default: m.BankJournal })),
);
const Review = lazy(() => import('../pages/bank/Review').then((m) => ({ default: m.Review })));
function Page({ children }: { children: ReactNode }) {
  return (
    <Suspense
      fallback={
        <Card>
          <p role="status">Открываем кабинет…</p>
        </Card>
      }
    >
      {children}
    </Suspense>
  );
}
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: boolean }> {
  state = { error: false };
  static getDerivedStateFromError() {
    return { error: true };
  }
  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error.message, info.componentStack);
  }
  render() {
    return this.state.error ? (
      <main className="shell">
        <EmptyState title="Не удалось открыть экран">
          <p>Обновите страницу. Сохранённые демо-заявки останутся в браузере.</p>
          <Action onClick={() => window.location.reload()}>Обновить</Action>
        </EmptyState>
      </main>
    ) : (
      this.props.children
    );
  }
}
function Layout({ role }: { role: 'bank' | 'client' }) {
  const { session, loading, signOut } = useSession();
  const action = useAction();
  const nav = useNavigate();
  const state = useCredit();
  const location = useLocation();
  useEffect(() => {
    if (location.hash) {
      const reveal = () => {
        const target = document.getElementById(location.hash.slice(1));
        if (!target) return false;
        target.scrollIntoView({ block: 'start' });
        return true;
      };
      if (reveal()) return;
      const observer = new MutationObserver(() => {
        if (reveal()) observer.disconnect();
      });
      observer.observe(document.getElementById('main') ?? document.body, {
        childList: true,
        subtree: true,
      });
      return () => observer.disconnect();
    }
    window.scrollTo(0, 0);
    document.getElementById('main')?.focus({ preventScroll: true });
  }, [location.pathname, location.hash]);
  if (loading)
    return (
      <main className="shell">
        <Card>
          <p role="status">Восстанавливаем вход…</p>
        </Card>
      </main>
    );
  if (!session)
    return (
      <Navigate
        to="/"
        replace
        state={{ returnTo: location.pathname + location.search + location.hash }}
      />
    );
  if (session.role !== role)
    return <Navigate to={session.role === 'bank' ? '/bank' : '/client'} replace />;
  const clientLinks = [
    ['/client', 'Главная'],
    ['/client/applications', 'Заявки'],
    ['/client/products', 'Продукты'],
    ['/client/documents', 'Документы'],
    ['/client/company', 'Компания'],
  ];
  const bankLinks = [
    ['/bank', 'Очередь'],
    ['/bank/mine', 'Мои разборы'],
    ['/bank/clients', 'Клиенты'],
    ['/bank/policies', 'Политики и модели'],
    ['/bank/journal', 'Журнал'],
  ];
  const openRequests = state.applications
    .filter((a) => a.companyId === session.profile && a.status === 'NEEDS_INFO')
    .reduce((n, a) => n + a.requests.filter((r) => r.state === 'OPEN').length, 0);
  return (
    <>
      <a href="#main" className="skip-link">
        К основному содержимому
      </a>
      <header className="header">
        <div className="header-inner">
          <div className="brand-group">
            <Brand />
            {role === 'bank' && <span className="bank-chip">Банк</span>}
            {role === 'client' &&
              location.pathname.startsWith('/client/new/') &&
              !state.storageError && <span className="header-draft">Черновик сохранён</span>}
          </div>
          <nav aria-label="Основная навигация">
            {(role === 'bank' ? bankLinks : clientLinks).map(([path, label]) => (
              <NavLink key={path} to={path} end={path === '/client' || path === '/bank'}>
                {label}
                {role === 'client' && path === '/client/applications' && openRequests > 0 && (
                  <span
                    className="nav-count"
                    aria-label={`Запросы, требующие ответа: ${openRequests}`}
                  >
                    {openRequests}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
          <button
            className="profile-button"
            type="button"
            disabled={action.busy}
            onClick={() =>
              action.run(async () => {
                await signOut();
                nav('/', { replace: true });
              })
            }
            aria-label="Выйти из кабинета"
            title="Выйти из кабинета"
          >
            <span className="avatar">
              {session.firstName[0]}
              {session.lastName[0]}
            </span>
            <span>
              <strong>
                {session.firstName} {session.lastName}
              </strong>
              <span className="block small">
                {role === 'bank'
                  ? 'Сотрудник банка'
                  : session.profile === 'karpov'
                    ? 'ИП Карпов'
                    : 'ООО «Зерно Опт»'}
              </span>
            </span>
            <LogOut aria-hidden size={17} />
          </button>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="shell">
        <ErrorState message={state.storageError ?? ''} />
        <ErrorState message={action.error} onRetry={action.retry} />
        <Outlet />
      </main>
      <footer className="shell footer">
        AURELIUS · Демо-условия. Подпись и выдача имитируются на демо-стенде.
      </footer>
    </>
  );
}
function Auxiliary({ kind }: { kind: 'company' | 'clients' | 'policies' }) {
  const state = useCredit();
  const { session } = useSession();
  if (kind === 'company')
    return (
      <>
        <h1>Компания</h1>
        <CompanyCard company={state.companies.find((c) => c.id === session!.profile)!} />
      </>
    );
  if (kind === 'clients')
    return (
      <>
        <h1>Клиенты</h1>
        <div className="two-columns">
          {state.companies.map((c) => (
            <div key={c.id}>
              <CompanyCard company={c} />
              <Card>
                <h3>Заявки</h3>
                {state.applications
                  .filter((a) => a.companyId === c.id)
                  .map((a) => (
                    <p key={a.id}>
                      <Link to={`/bank/applications/${a.id}`}>{a.id}</Link>
                    </p>
                  ))}
              </Card>
            </div>
          ))}
        </div>
      </>
    );
  if (kind === 'policies')
    return (
      <>
        <h1>Политики и модели</h1>
        <Card>
          <h2>policy-2026.10</h2>
          <p>
            Минимальное покрытие платежей — 1,3×. Свободный поток делится на сумму действующих
            платежей и нового платежа. Недостаток данных направляет заявку на уточнение; сбой
            источника — в ожидание.
          </p>
          <h2>score-model v0.3 · демо</h2>
          <p>
            PD 12 месяцев 4,8% для ООО «Зерно Опт» — синтетическое значение из макета. Реальные
            модели и банковские решения не подключены.
          </p>
        </Card>
      </>
    );
  return null;
}
export function App() {
  const { session } = useSession();
  const location = useLocation();
  const [assistant, setAssistant] = useState(false);
  const [assistantSeed, setAssistantSeed] = useState<string>();
  useEffect(() => {
    setAssistant(false);
    setAssistantSeed(undefined);
  }, [session?.role, session?.profile]);
  const openAssistant = (seed?: string) => {
    setAssistantSeed(seed);
    setAssistant(true);
  };
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/client" element={<Layout role="client" />}>
          <Route index element={<Home onAssistant={() => openAssistant()} />} />
          <Route path="applications" element={<Applications />} />
          <Route
            path="applications/:id"
            element={
              <Page>
                <ApplicationDetail />
              </Page>
            }
          />
          <Route
            path="new/:id"
            element={
              <Page>
                <ApplicationForm />
              </Page>
            }
          />
          <Route path="products" element={<Products onAssistant={openAssistant} />} />
          <Route path="documents" element={<Documents />} />
          <Route path="company" element={<Auxiliary kind="company" />} />
        </Route>
        <Route path="/bank" element={<Layout role="bank" />}>
          <Route
            index
            element={
              <Page>
                <Queue />
              </Page>
            }
          />
          <Route
            path="mine"
            element={
              <Page>
                <Queue mine />
              </Page>
            }
          />
          <Route
            path="applications/:id"
            element={
              <Page>
                <Review />
              </Page>
            }
          />
          <Route
            path="journal"
            element={
              <Page>
                <BankJournal />
              </Page>
            }
          />
          <Route path="clients" element={<Auxiliary kind="clients" />} />
          <Route path="policies" element={<Auxiliary kind="policies" />} />
        </Route>
        <Route
          path="*"
          element={
            <main className="shell">
              <EmptyState title="Такой страницы нет">
                <Link to="/">На экран входа</Link>
              </EmptyState>
            </main>
          }
        />
      </Routes>
      {session?.role === 'client' && location.pathname.startsWith('/client') && (
        <button
          type="button"
          id="assistant-launcher"
          className="assistant-launcher"
          aria-label={assistant ? 'Свернуть чат с помощником' : 'Открыть чат с помощником'}
          aria-expanded={assistant}
          aria-controls={assistant ? 'assistant-chat' : undefined}
          onClick={() => setAssistant((old) => !old)}
        >
          {assistant ? (
            <ChevronDown aria-hidden size={21} />
          ) : (
            <MessageCircle aria-hidden size={21} />
          )}
          <span>{assistant ? 'Свернуть' : 'Помощник'}</span>
        </button>
      )}
      <AssistantPanel
        key={`${session?.role}-${session?.profile}`}
        open={assistant && session?.role === 'client' && location.pathname.startsWith('/client')}
        onOpenChange={setAssistant}
        seed={assistantSeed}
      />
    </ErrorBoundary>
  );
}
