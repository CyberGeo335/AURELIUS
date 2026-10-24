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
import { ArrowUpRight, Building2, UserRound, RotateCcw, MessageCircle } from 'lucide-react';
import { useAction, useApi, useCredit, useSession } from './context';
import {
  Action,
  Card,
  CompanyCard,
  EmptyState,
  ErrorState,
  HeroPanel,
} from '../components/v2/primitives';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
  DialogClose,
} from '../components/ui/dialog';
import { AssistantPanel } from '../components/v2/AssistantPanel';
import { Home, Applications, ProductList } from '../pages/client/Home';
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
function Logo() {
  return (
    <Link to="/" className="logo">
      <span aria-hidden />
      кредитный кабинет
    </Link>
  );
}
function Login() {
  const { login } = useSession();
  const nav = useNavigate();
  const api = useApi();
  const action = useAction();
  const [resetOpen, setResetOpen] = useState(false);
  return (
    <>
      <header className="header">
        <div className="header-inner">
          <Logo />
          <span className="header-note">AURELIUS · демо-стенд</span>
        </div>
      </header>
      <main className="shell login">
        <div className="login-intro">
          <p className="eyebrow">Альфа Будущее · 2026</p>
          <h1>
            Решения для бизнеса.
            <br />
            Понятно на каждом шаге.
          </h1>
          <p className="muted">
            От первой заявки до решения банка — один кабинет.
            <br />
            Выберите роль, чтобы пройти демонстрационный сценарий.
          </p>
        </div>
        <div className="login-grid">
          <HeroPanel>
            <UserRound aria-hidden size={32} />
            <h2>Я предприниматель</h2>
            <p>Подать заявку, уточнить данные и выбрать условия.</p>
            <div className="stack">
              <Action
                tone="white"
                onClick={() => {
                  login({ role: 'client', profile: 'karpov' });
                  nav('/client');
                }}
              >
                ИП Карпов <ArrowUpRight aria-hidden size={18} />
              </Action>
              <Action
                tone="outline"
                onClick={() => {
                  login({ role: 'client', profile: 'zerno' });
                  nav('/client');
                }}
              >
                ООО «Зерно Опт» <ArrowUpRight aria-hidden size={18} />
              </Action>
            </div>
          </HeroPanel>
          <Card className="dark">
            <Building2 aria-hidden size={32} />
            <h2>Я сотрудник банка</h2>
            <p className="muted">
              Разобрать заявку, оценить причины остановки и предложить решение.
            </p>
            <div className="analyst">
              <span className="avatar">АС</span>
              <span>
                <strong>Анна Смирнова</strong>
                <span className="block muted small">Кредитный аналитик</span>
              </span>
            </div>
            <Action
              tone="white"
              onClick={() => {
                login({ role: 'bank', profile: 'karpov' });
                nav('/bank');
              }}
            >
              Открыть очередь <ArrowUpRight aria-hidden size={18} />
            </Action>
          </Card>
        </div>
        <div className="spread">
          <p className="small muted">
            Все сведения синтетические. Решения, подпись и выдача — имитация.
            <br />
            Действия ролей синхронизируются в этом браузере, в том числе между вкладками.
          </p>
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
              <ErrorState message={action.error} />
              <Action
                disabled={action.busy}
                onClick={() =>
                  action.run(async () => {
                    await api.reset();
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
function Layout({ role, onAssistant }: { role: 'bank' | 'client'; onAssistant: () => void }) {
  const { session, login } = useSession();
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
  if (!session || session.role !== role) return <Navigate to="/" replace />;
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
  return (
    <>
      <a href="#main" className="skip-link">
        К основному содержимому
      </a>
      <header className="header">
        <div className="header-inner">
          <div className="brand-group">
            <Logo />
            {role === 'bank' && <span className="bank-chip">Банк</span>}
          </div>
          <nav aria-label="Основная навигация">
            {(role === 'bank' ? bankLinks : clientLinks).map(([path, label]) => (
              <NavLink key={path} to={path} end={path === '/client' || path === '/bank'}>
                {label}
              </NavLink>
            ))}
          </nav>
          <Link className="profile-button" to="/" onClick={() => login(null)} title="Сменить роль">
            <span className="avatar">
              {role === 'bank' ? 'АС' : session.profile === 'karpov' ? 'ИК' : 'ЗО'}
            </span>
            <span>
              {role === 'bank'
                ? 'Анна Смирнова'
                : session.profile === 'karpov'
                  ? 'ИП Карпов И. С.'
                  : 'ООО «Зерно Опт»'}
              <span className="block small">Сменить роль</span>
            </span>
          </Link>
        </div>
      </header>
      <main id="main" tabIndex={-1} className="shell">
        <ErrorState message={state.storageError ?? ''} />
        <Outlet />
      </main>
      <footer className="shell footer">
        AURELIUS · Демо-условия. Подпись и выдача имитируются на демо-стенде.
        {role === 'client' && (
          <Action tone="white" onClick={onAssistant}>
            <MessageCircle aria-hidden size={18} />
            Помощник
          </Action>
        )}
      </footer>
    </>
  );
}
function Auxiliary({ kind }: { kind: 'company' | 'documents' | 'clients' | 'policies' }) {
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
  const apps = state.applications.filter((a) => a.companyId === session!.profile);
  return (
    <>
      <h1>Документы</h1>
      <Card>
        <h2>Файлы и согласия по заявкам</h2>
        {apps.length ? (
          apps.map((a) => (
            <div className="document-row" key={a.id}>
              <Link to={`/client/applications/${a.id}`}>{a.id}</Link>
              <p>{a.files.length ? a.files.join(', ') : 'Файлы не добавлены'}</p>
              <p className="small muted">
                БКИ: {a.consentBki ? 'согласие получено отдельно' : 'согласие не дано'} ·{' '}
                {a.consentVersion ?? 'черновик'}
              </p>
            </div>
          ))
        ) : (
          <p>Здесь появятся документы ваших заявок.</p>
        )}
        <p className="small muted">
          В демо сохраняются только имена файлов. Подписанные договоры и реальные документы не
          создаются.
        </p>
      </Card>
    </>
  );
}
export function App() {
  const [assistant, setAssistant] = useState(false);
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route
          path="/client"
          element={<Layout role="client" onAssistant={() => setAssistant(true)} />}
        >
          <Route index element={<Home onAssistant={() => setAssistant(true)} />} />
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
          <Route
            path="products"
            element={
              <>
                <h1>Продукты для бизнеса</h1>
                <ProductList />
              </>
            }
          />
          <Route path="documents" element={<Auxiliary kind="documents" />} />
          <Route path="company" element={<Auxiliary kind="company" />} />
        </Route>
        <Route path="/bank" element={<Layout role="bank" onAssistant={() => {}} />}>
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
      <AssistantPanel open={assistant} onOpenChange={setAssistant} />
    </ErrorBoundary>
  );
}
