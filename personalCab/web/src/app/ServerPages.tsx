import { useEffect, useState, type ReactNode } from 'react';
import { Link, NavLink, useLocation, useNavigate } from 'react-router';
import { IntegratedCabinet } from './IntegratedCabinet';
import {
  HttpV2Api,
  type AuditV2,
  type DocumentV2,
  type StateV2,
  type ViewV2,
} from '../api/HttpV2Api';
import { Action, Card, EmptyState, ErrorState, HeroPanel } from '../components/v2/primitives';
import { Brand } from '../components/v2/Brand';

const api = new HttpV2Api();
export const stageNames: Record<string, string> = {
  DRAFT: 'Черновик',
  NEEDS_INFO: 'Нужны данные',
  CHECKING: 'Проверяем',
  MANUAL_REVIEW: 'Ручное рассмотрение',
  OFFERED: 'Предложение DEMO',
  ACCEPTED: 'Принято',
  EXECUTED_DEMO: 'Исполнено DEMO',
  DECLINED: 'Отказ',
  CANCELLED: 'Отменено',
};
const rub = (n: unknown) => (n == null ? 'Не указано' : Number(n).toLocaleString('ru-RU') + ' ₽');
export interface ServerRoute {
  path: string;
  caseId?: string;
  step: number;
  navigate: (path: string) => void;
}
export function ServerCabinet() {
  const location = useLocation();
  const navigate = useNavigate();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.getElementById('main')?.focus({ preventScroll: true });
  }, [location.pathname, location.search]);
  const match = location.pathname.match(
    /^\/(client\/(?:applications|new)|bank\/applications)\/([^/]+)$/,
  );
  const step = Math.max(
    0,
    Math.min(3, Number(new URLSearchParams(location.search).get('step')) || 0),
  );
  return (
    <IntegratedCabinet route={{ path: location.pathname, caseId: match?.[2], step, navigate }} />
  );
}
export function ServerNavigation({
  state,
  logout,
  busy,
}: {
  state: StateV2;
  logout: () => Promise<void>;
  busy: boolean;
}) {
  const bank = state.session.role === 'OPERATOR';
  const links = bank
    ? [
        ['/bank', 'Очередь'],
        ['/bank/mine', 'Мои разборы'],
        ['/bank/clients', 'Клиенты'],
        ['/bank/policies', 'Политики и модели'],
        ['/bank/journal', 'Журнал'],
      ]
    : [
        ['/client', 'Главная'],
        ['/client/applications', 'Заявки'],
        ['/client/products', 'Продукты'],
        ['/client/documents', 'Документы'],
        ['/client/company', 'Компания'],
      ];
  return (
    <header className="header">
      <div className="header-inner">
        <Brand />
        {bank && <span className="bank-chip">Банк</span>}
        <nav aria-label="Основная навигация">
          {links.map(([to, label]) => (
            <NavLink key={to} to={to} end>
              {label}
            </NavLink>
          ))}
        </nav>
        <span>
          {state.session.full_name} · {bank ? 'Сотрудник банка' : 'Клиент'}
        </span>
        <button disabled={busy} onClick={() => void logout()}>
          Выйти
        </button>
      </div>
    </header>
  );
}
export function WizardNavigation({ route }: { route: ServerRoute }) {
  const steps = ['Цель и сумма', 'Бизнес и документы', 'Согласия', 'Проверка и отправка'];
  return (
    <Card>
      <Link to="/client/applications">← К заявкам</Link>
      <h1>Заявка на финансирование</h1>
      <nav className="server-steps" aria-label="Шаги заявки">
        {steps.map((label, i) => (
          <Link
            key={label}
            aria-current={i === route.step ? 'step' : undefined}
            to={route.path + '?step=' + i}
          >
            {i + 1}. {label}
          </Link>
        ))}
      </nav>
      <p>
        Шаг {route.step + 1} из 4. Данные сохраняются на сервере после нажатия кнопки сохранения.
      </p>
    </Card>
  );
}
export function DocumentCoverage({ document: d }: { document: DocumentV2 }) {
  return (
    <div className="server-document">
      <strong>{d.filename}</strong>
      <p>
        {d.status} · SHA-256 {d.sha256.slice(0, 12)}
      </p>
      {d.statement && (
        <>
          <p>
            Покрытие выписки: {d.statement.covered_months}/12 завершённых месяцев ·{' '}
            {d.statement.status}
          </p>
          {d.statement.missing_months.length > 0 && (
            <p>Не представлены: {d.statement.missing_months.join(', ')}</p>
          )}
          {d.statement.duplicate_months.length > 0 && (
            <p role="alert">Повторяющиеся периоды: {d.statement.duplicate_months.join(', ')}</p>
          )}
          {d.statement.issues.map((issue) => (
            <p key={issue} role="alert">
              {issue}
            </p>
          ))}
          <p className="small muted">
            Периоды получены из файла клиента. Полнота оборотов бизнеса и суммы не подтверждены.
          </p>
        </>
      )}
    </div>
  );
}
function CaseList({
  state,
  bank = false,
  filter = '',
}: {
  state: StateV2;
  bank?: boolean;
  filter?: string;
}) {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState('ALL');
  const [product, setProduct] = useState('ALL');
  const [conflicts, setConflicts] = useState(false);
  const cases = state.cases.filter(
    (c) =>
      (!filter || c.review_owner === state.session.login) &&
      (status === 'ALL' || c.status === status) &&
      (product === 'ALL' || c.selected_product_id === product) &&
      (!conflicts ||
        c.data_resolution.gaps.some((g) => g.status === 'CONFLICT') ||
        c.has_pending_changes ||
        !!c.field_changes?.some((ch) => ch.review_status === 'PENDING')) &&
      (
        c.case_id +
        ' ' +
        state.companies.find(
          (co) =>
            co.company_id === Number(c.request.borrower_id?.toString().replace('company-', '')),
        )?.name +
        ' ' +
        JSON.stringify(c.request)
      )
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  return (
    <Card>
      <h2>{bank ? 'Очередь рассмотрения' : 'Мои заявки'}</h2>
      <div className="server-filters">
        <label>
          Поиск заявки
          <input
            aria-label="Поиск заявки"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Компания или номер заявки"
          />
        </label>
        <label>
          Этап
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="ALL">Все этапы</option>
            {Object.entries(stageNames).map(([v, l]) => (
              <option key={v} value={v}>
                {l}
              </option>
            ))}
          </select>
        </label>
        <label>
          Продукт
          <select value={product} onChange={(e) => setProduct(e.target.value)}>
            <option value="ALL">Все продукты</option>
            {[...new Set(state.cases.map((c) => c.selected_product_id).filter(Boolean))].map(
              (p) => (
                <option key={p} value={p!}>
                  {p}
                </option>
              ),
            )}
          </select>
        </label>
        {bank && (
          <label>
            <input
              type="checkbox"
              checked={conflicts}
              onChange={(e) => setConflicts(e.target.checked)}
            />
            Только изменения и конфликты
          </label>
        )}
      </div>
      <div className="table-scroll">
        <table className="queue-table">
          <thead>
            <tr>
              <th>Заявка</th>
              <th>Параметры</th>
              <th>Этап</th>
              <th>{bank ? 'Оценка и сотрудник' : 'Продукт'}</th>
              <th>Действие</th>
            </tr>
          </thead>
          <tbody>
            {cases.map((c) => (
              <tr key={c.case_id}>
                <td>
                  {c.case_id}
                  <p>
                    {
                      state.companies.find(
                        (co) => 'company-' + co.company_id === c.request.borrower_id,
                      )?.name
                    }
                  </p>
                </td>
                <td>
                  {rub(c.request.amount_rub)} · {c.request.term_months ?? '—'} мес.
                </td>
                <td>{stageNames[c.status] ?? c.status}</td>
                <td>
                  {bank ? (
                    <>
                      {c.assessment?.probability == null
                        ? 'Нет оценки'
                        : (c.assessment.probability * 100).toFixed(2) + '%'}
                      <p>{c.review_owner ?? 'Не назначен'}</p>
                    </>
                  ) : (
                    (c.selected_product_id ?? 'Не выбран')
                  )}
                </td>
                <td>
                  <Action tone="soft" asChild>
                    <Link to={(bank ? '/bank' : '/client') + '/applications/' + c.case_id}>
                      {bank ? 'Разобрать' : 'Открыть'}
                    </Link>
                  </Action>
                  {!bank && c.status === 'DRAFT' && (
                    <p>
                      <Link to={'/client/new/' + c.case_id}>Продолжить анкету</Link>
                    </p>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!cases.length && (
        <EmptyState title="По этому фильтру заявок нет">
          <p>Измените поиск или создайте новую заявку.</p>
        </EmptyState>
      )}
    </Card>
  );
}
function Catalog({
  create,
  busy,
  showModels = false,
}: {
  create: () => void;
  busy: boolean;
  showModels?: boolean;
}) {
  const [catalog, setCatalog] = useState<Awaited<ReturnType<HttpV2Api['catalog']>> | null>(null);
  const [error, setError] = useState('');
  const load = () =>
    api
      .catalog()
      .then((v) => {
        setCatalog(v);
        setError('');
      })
      .catch((e) => setError(e.message));
  useEffect(() => {
    void load();
  }, []);
  return (
    <>
      <h1>Продукты и условия</h1>
      <ErrorState message={error} onRetry={() => void load()} />
      <p>
        Все направления каталога. Подбор и опубликованные условия не являются кредитным решением.
      </p>
      <p className="small muted">Версия: {catalog?.catalog_version ?? 'загрузка'}</p>
      <div className="server-product-grid">
        {catalog?.candidates.map((c) => (
          <Card key={c.product_id}>
            <h2>{c.name}</h2>
            <p>
              {c.database_supported
                ? 'Доступен серверный маршрут'
                : 'Бизнес-адаптер этого направления отсутствует'}
            </p>
            <p>
              Условия: {c.source_conditions?.validity ?? 'UNKNOWN'} ·{' '}
              {c.source_conditions?.approval_version ?? 'утверждённая policy неизвестна'}
            </p>
            <p>{c.source_version}</p>
            {c.source_url && (
              <a href={c.source_url} target="_blank" rel="noreferrer">
                Источник условий
              </a>
            )}
            <details>
              <summary>Условия, требования и ограничения</summary>
              {c.limitations?.map((l) => (
                <p key={l}>{l}</p>
              ))}
              {c.source_conditions?.terms?.map((t, i) => (
                <ProductTerms key={i} terms={t} />
              ))}
            </details>
            {!showModels && (
              <Action disabled={busy} onClick={create}>
                Новая заявка
              </Action>
            )}
          </Card>
        ))}
      </div>
      {showModels && catalog?.model_registry && (
        <Card>
          <h2>Реестр моделей DEMO</h2>
          <p>
            {catalog.model_registry.version} ·{' '}
            {catalog.model_registry.available ? 'доступен' : 'недоступен'}
          </p>
          {catalog.model_registry.models.map((m, i) => (
            <div key={i}>
              <h3>{String(m.model_id)}</h3>
              <p>
                Тип: {String(m.kind)} · цель: {String(m.target)}
              </p>
              <p>
                Продукты: {String(m.supported_products)} · сроки обучения:{' '}
                {String(m.supported_term_months)} мес.
              </p>
              <p>Версия артефакта: {String(m.sha256)}</p>
            </div>
          ))}
          <p>
            Утверждения для реального кредитования нет. Банковская policy и её пороги применяются
            только при наличии утверждённой версии.
          </p>
        </Card>
      )}
    </>
  );
}
function ProductTerms({ terms: t }: { terms: Record<string, unknown> }) {
  const display = (value: unknown) =>
    value == null ? 'не определено' : Array.isArray(value) ? value.join(', ') : String(value);
  const unit = (value: unknown) =>
    value === 'MONTHS' ? 'мес.' : value === 'DAYS' ? 'дн.' : 'единица не задана';
  const labels: Record<string, string> = {
    min_amount: 'Минимальная сумма, ₽',
    max_amount: 'Максимальная сумма, ₽',
    drawdown_period_months: 'Окно выборки, месяцев',
    min_business_age_months: 'Минимальный возраст бизнеса, месяцев',
    allowed_entity_types: 'Формы бизнеса по источнику',
    requires_collateral: 'Требование залога',
    source_checked_at: 'Дата проверки источника',
    effective_from: 'Условия с',
    effective_to: 'Условия до',
  };
  return (
    <div className="server-document">
      <h4>Версия {display(t.version_code)}</h4>
      <dl>
        {Object.entries(labels).map(([key, label]) => (
          <div key={key}>
            <dt>{label}</dt>
            <dd>{display(t[key])}</dd>
          </div>
        ))}
      </dl>
      <p>
        Срок договора: {display(t.min_contract_term_value)} — {display(t.max_contract_term_value)}{' '}
        {unit(t.contract_term_unit)}
      </p>
      <p>
        Срок транша: {display(t.min_tranche_term_value)} — {display(t.max_tranche_term_value)}{' '}
        {unit(t.tranche_term_unit)}
      </p>
      {[
        'credit_product_rate_options',
        'credit_product_fees',
        'credit_product_repayment_options',
      ].map((key) =>
        Array.isArray(t[key]) && t[key].length > 0 ? (
          <details key={key}>
            <summary>
              {key === 'credit_product_rate_options'
                ? 'Опубликованные ставки'
                : key === 'credit_product_fees'
                  ? 'Опубликованные комиссии'
                  : 'Способы погашения'}
            </summary>
            {(t[key] as Record<string, unknown>[]).map((row, i) => (
              <dl key={i}>
                {Object.entries(row)
                  .filter(([k]) => !k.endsWith('_id'))
                  .map(([k, v]) => (
                    <div key={k}>
                      <dt>{k}</dt>
                      <dd>{display(v)}</dd>
                    </div>
                  ))}
              </dl>
            ))}
          </details>
        ) : null,
      )}
      <p>Опубликованная ставка не является договорной ставкой вашего предложения.</p>
    </div>
  );
}
export function AuditJournal({ caseId }: { caseId?: string }) {
  const [data, setData] = useState<AuditV2 | null>(null);
  const [error, setError] = useState('');
  const load = async (cursor?: string) => {
    try {
      const next = await api.audit(caseId, cursor);
      setData((old) =>
        cursor && old ? { ...next, events: [...old.events, ...next.events] } : next,
      );
      setError('');
    } catch (e) {
      setError((e as Error).message);
    }
  };
  useEffect(() => {
    void load();
  }, [caseId]); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <Card>
      <h2>Журнал аудита</h2>
      <ErrorState message={error} onRetry={() => void load()} />
      <Action tone="soft" onClick={() => void load()}>
        Обновить журнал
      </Action>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Время / действие</th>
              <th>Заявка / версия</th>
              <th>Сотрудник или клиент</th>
              <th>Основания</th>
            </tr>
          </thead>
          <tbody>
            {data?.events.map((e) => (
              <tr key={e.id}>
                <td>
                  {new Date(e.created_at).toLocaleString('ru-RU')}
                  <p>{e.action}</p>
                </td>
                <td>
                  <Link to={'/bank/applications/' + e.case_id}>{e.case_id}</Link>
                  <p>
                    v{e.version} · ревизия {e.revision}
                  </p>
                </td>
                <td>{e.actor_id}</td>
                <td>
                  <details>
                    <summary>Источники и результат</summary>
                    <pre>{JSON.stringify(e.metadata, null, 2)}</pre>
                  </details>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data?.next_cursor && (
        <Action onClick={() => void load(data.next_cursor!)}>Загрузить более ранние</Action>
      )}
      <details>
        <summary>Выдача и отзыв разрешений</summary>
        {data?.consent_events.map((e) => (
          <p key={e.id}>
            {e.created_at} · {e.actor_id} · {e.action} · {e.scope}
          </p>
        ))}
      </details>
    </Card>
  );
}
export function ServerPage({
  route,
  state,
  busy,
  create,
}: {
  route: ServerRoute;
  state: StateV2;
  busy: boolean;
  create: () => void;
}) {
  const path = route.path,
    bank = state.session.role === 'OPERATOR';
  if (path === '/client/products' || path === '/bank/policies')
    return <Catalog busy={busy} create={create} showModels={path === '/bank/policies'} />;
  if (path === '/bank/journal')
    return (
      <>
        <h1>Журнал действий</h1>
        <AuditJournal />
      </>
    );
  if (path === '/client/documents')
    return (
      <>
        <h1>Документы</h1>
        {state.cases.map((c) => (
          <Card key={c.case_id}>
            <Link to={'/client/applications/' + c.case_id}>{c.case_id}</Link>
            {(c.current_data ?? c.data_context)?.documents.map((d) => (
              <DocumentCoverage key={d.document_id} document={d} />
            ))}
            <p>Добавить файл можно в анкете соответствующей заявки.</p>
          </Card>
        ))}
      </>
    );
  if (path === '/client/company' || path === '/bank/clients')
    return (
      <>
        <h1>{bank ? 'Клиенты' : 'Компания'}</h1>
        {state.companies.map((c) => (
          <Card key={c.company_id}>
            <h2>{c.name}</h2>
            <p>ИНН: {c.inn}</p>
            <p>Компания №{c.company_id}</p>
            {state.cases
              .filter((a) => a.request.borrower_id === 'company-' + c.company_id)
              .map((a) => (
                <p key={a.case_id}>
                  <Link to={(bank ? '/bank' : '/client') + '/applications/' + a.case_id}>
                    {a.case_id}
                  </Link>
                </p>
              ))}
          </Card>
        ))}
      </>
    );
  const home = path === '/client',
    queue = path === '/bank' || path === '/bank/mine';
  if (!home && !queue && path !== '/client/applications')
    return (
      <EmptyState title="Такой страницы нет">
        <Link to={bank ? '/bank' : '/client'}>В кабинет</Link>
      </EmptyState>
    );
  return (
    <>
      {(home || queue) && (
        <div className="server-hero">
          <HeroPanel symbol={String(state.cases.length)}>
            <p className="hero-eyebrow">AURELIUS · DEMO</p>
            <h1>{bank ? 'Рассмотрение заявок' : 'Финансирование вашего бизнеса'}</h1>
            <p>
              {bank
                ? 'Проверьте досье и фактическую оценку. Решение сохраняется сотрудником явно.'
                : 'Начните заявку, заполните анкету или обсудите задачу с помощником. Все экраны используют один серверный кейс.'}
            </p>
            {!bank && (
              <Action tone="white" disabled={busy} onClick={create}>
                Новая заявка
              </Action>
            )}
          </HeroPanel>
          <Card>
            <h2>Текущие обращения</h2>
            <p>Всего: {state.cases.length}</p>
            <p>Нужен ответ: {state.cases.filter((c) => c.status === 'NEEDS_INFO').length}</p>
            <p>На рассмотрении: {state.cases.filter((c) => c.status === 'MANUAL_REVIEW').length}</p>
            <p>Предложения: {state.cases.filter((c) => c.status === 'OFFERED').length}</p>
          </Card>
        </div>
      )}
      {!home && !queue && (
        <>
          <h1>Заявки</h1>
          <Action disabled={busy} onClick={create}>
            Новая заявка
          </Action>
        </>
      )}
      <CaseList state={state} bank={bank} filter={path === '/bank/mine' ? 'mine' : ''} />
    </>
  );
}
export function CaseWorkspace({ children }: { children: ReactNode }) {
  return <div className="server-workspace">{children}</div>;
}

export function ReviewEvidence({
  view,
  login,
  busy,
  save,
}: {
  view: ViewV2;
  login: string;
  busy: boolean;
  save: (kind: string, args: Record<string, unknown>) => Promise<boolean>;
}) {
  const enabled = (kind: string) => !busy && !!view.allowed_operations?.includes(kind);
  const [error, setError] = useState('');
  return (
    <Card>
      <h3>Ответственный и проверка сведений</h3>
      <p>Разбор: {view.review_owner ?? 'не назначен'}</p>
      <div className="actions">
        <Action tone="soft" disabled={!enabled('claim')} onClick={() => void save('claim', {})}>
          Взять в работу
        </Action>
        <Action tone="soft" disabled={!enabled('release')} onClick={() => void save('release', {})}>
          Освободить разбор
        </Action>
      </div>
      {view.review_owner && view.review_owner !== login && (
        <p>Изменения доступны назначенному сотруднику.</p>
      )}
      <h4>Полномочия заявителя</h4>
      <p>
        {view.authority_evidence
          ? `${view.authority_evidence.verified ? 'Подтверждены' : 'Не подтверждены'} · ${view.authority_evidence.source_ref} · ${view.authority_evidence.reviewed_by}`
          : 'Документальная проверка полномочий не сохранена.'}
      </p>
      <form
        className="form-fields"
        onSubmit={async (e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          try {
            setError('');
            const available = new Date(String(form.get('authorityTime')));
            await save('authority', {
              verified: form.get('verified') === 'true',
              source_ref: String(form.get('authoritySource')),
              available_at: available.toISOString(),
            });
          } catch {
            setError('Проверьте время и источник полномочий.');
          }
        }}
      >
        <label>
          Результат проверки
          <select name="verified">
            <option value="true">Подтверждены по документу</option>
            <option value="false">Не подтверждены</option>
          </select>
        </label>
        <label>
          Документ / источник полномочий
          <input name="authoritySource" required />
        </label>
        <label>
          Источник доступен с<input name="authorityTime" type="datetime-local" required />
        </label>
        <Action tone="soft" disabled={!enabled('authority')}>
          Сохранить проверку полномочий
        </Action>
      </form>
      <p className="small muted">Запись о документе не предоставляет новых прав входа в систему.</p>
      <details>
        <summary>Разрешение конфликта формы бизнеса</summary>
        <form
          className="form-fields"
          onSubmit={async (e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            try {
              setError('');
              await save('profile_resolution', {
                legal_form: form.get('resolvedForm'),
                source_ref: String(form.get('profileSource')),
                available_at: new Date(String(form.get('profileTime'))).toISOString(),
              });
            } catch {
              setError('Проверьте время и подтверждающий источник.');
            }
          }}
        >
          <label>
            Проверенная форма
            <select name="resolvedForm">
              {['IP', 'OOO', 'AO', 'OTHER'].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Источник решения
            <input name="profileSource" required />
          </label>
          <label>
            Источник известен с<input name="profileTime" type="datetime-local" required />
          </label>
          <Action tone="soft" disabled={!enabled('profile_resolution')}>
            Сохранить разрешение конфликта
          </Action>
        </form>
        <p>
          После проверки источника клиент обновляет профиль и сведения. Параметры его запроса не
          заменяются решением сотрудника.
        </p>
      </details>
      <ErrorState message={error} />
      <details open={!!view.field_changes?.some((c) => c.review_status === 'PENDING')}>
        <summary>Изменения клиента и конфликты</summary>
        {view.client_changes?.map((c, i) => (
          <p key={i}>
            {c.field}: {String(c.old_value ?? '—')} → {String(c.new_value)} · ревизия {c.revision} ·{' '}
            {c.source} · {c.review_status ?? 'PENDING'}
          </p>
        ))}
        {view.field_changes?.map((c) => (
          <p key={c.change_id}>
            {c.field_code}: {String(c.old_value ?? '—')} → {String(c.new_value)} · {c.review_status}{' '}
            · {c.source_ref ?? 'источник не проверен'}
          </p>
        ))}
        <p>
          Сверьте изменение с источником и подтвердите соответствующее поле в форме ниже. Заявленные
          сведения не становятся проверенными от открытия досье.
        </p>
        <form
          className="form-fields"
          onSubmit={async (e) => {
            e.preventDefault();
            const f = new FormData(e.currentTarget);
            await save('review_changes', {
              fields: f.getAll('changedField').map(String),
              source_ref: String(f.get('changeSource')),
            });
          }}
        >
          {[
            ...new Set(
              view.client_changes
                ?.filter((c) => c.review_status !== 'REVIEWED')
                .map((c) => c.field) ?? [],
            ),
          ].map((field) => (
            <label key={field}>
              <input type="checkbox" name="changedField" value={field} />
              {field}
            </label>
          ))}
          <label>
            Источник сверки изменений
            <input name="changeSource" required />
          </label>
          <Action tone="soft" disabled={!enabled('review_changes')}>
            Отметить сверку изменений
          </Action>
        </form>
      </details>
    </Card>
  );
}
export function OfferComparison({ view }: { view: ViewV2 }) {
  if (!view.offer_history?.length) return null;
  return (
    <Card>
      <h3>Сравнение предложений</h3>
      <p>
        Запрошено: {rub(view.request.amount_rub)} · {view.request.term_months ?? '—'} мес.
        Исторические предложения показаны для сравнения.
      </p>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Ревизия</th>
              <th>Сумма и срок</th>
              <th>Ставка и комиссии</th>
              <th>Условия и срок действия</th>
              <th>Актуальность</th>
            </tr>
          </thead>
          <tbody>
            {view.offer_history.map((h) => (
              <tr key={h.offer.offer_id}>
                <td>{h.revision}</td>
                <td>
                  {rub(h.offer.amount_rub)} · {h.offer.term_months} мес.
                </td>
                <td>
                  {Number(h.offer.annual_rate_fraction) * 100}% годовых
                  <p>{h.offer.fees_rub.map((f) => rub(f)).join(' + ') || '0 ₽'}</p>
                </td>
                <td>
                  {h.offer.conditions.join('; ') || 'нет дополнительных условий'}
                  <p>До {new Date(h.offer.expires_at).toLocaleString('ru-RU')}</p>
                  <p>
                    {h.offer.repayment_type === 'ANNUITY'
                      ? 'Аннуитетная выдача DEMO'
                      : 'Открытие лимита DEMO'}
                  </p>
                </td>
                <td>
                  {h.invalidated_at
                    ? 'Отозвано после изменения сведений'
                    : new Date(h.offer.expires_at) <= new Date()
                      ? 'Истекло'
                      : 'Текущая ревизия'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p>
        При изменении суммы или срока предложения оценка исходного запроса не оценивает новые
        параметры автоматически.
      </p>
    </Card>
  );
}
