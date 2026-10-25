import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { useApi, useCredit, useSession, useAction } from '../app/context';
import { HttpCreditApi } from '../api/HttpCreditApi';
import {
  Action,
  Card,
  EmptyState,
  ErrorState,
  HeroPanel,
  KeyValue,
  StatusBadge,
} from '../components/v2/primitives';
import { Input } from '../components/ui/input';
import { Textarea } from '../components/ui/textarea';
import { money } from '../domain/finance';
import { products, type Application, type Company, type ServerRequirement } from '../domain/types';

function requestedAmount(app: Application) {
  return app.server?.requested_amount === null ? 'Сумма не указана' : money(app.amount);
}
function requestedTerm(app: Application) {
  return app.server?.requested_term_months === null ? 'Срок не указан' : `${app.term} мес.`;
}
function requirements(rows: ServerRequirement[], app: Application, company: Company) {
  return rows.filter(
    (r) =>
      r.product_code === app.product && (company.entity === 'IP' ? r.required_ip : r.required_ooo),
  );
}
export function BusinessProducts() {
  const state = useCredit();
  const api = useApi();
  const { session } = useSession();
  const nav = useNavigate();
  const action = useAction();
  return (
    <Card>
      <h2>Финансирование бизнеса</h2>
      <ErrorState message={action.error} onRetry={action.retry} />
      {state.catalog?.map((row) => {
        const code = row.product_code as keyof typeof products;
        return (
          <div className="product-row" key={String(row.terms_id)}>
            <div>
              <h3>{products[code]}</h3>
              <p className="muted">
                {row.min_amount == null ? '' : `От ${money(Number(row.min_amount))}`}{' '}
                {row.max_amount == null ? '' : `до ${money(Number(row.max_amount))}`}
              </p>
              <p>
                {row.min_contract_term_value == null
                  ? ''
                  : `Срок: ${row.min_contract_term_value}–${row.max_contract_term_value} ${row.contract_term_unit === 'MONTHS' ? 'мес.' : 'дней'}`}
              </p>
            </div>
            <Action
              disabled={action.busy}
              onClick={() =>
                void action.run(async () => {
                  const id = await api.createDraft(session!.profile, code);
                  nav(`/client/new/${id}`);
                })
              }
            >
              Новая заявка
            </Action>
          </div>
        );
      })}
    </Card>
  );
}
export function BusinessHome() {
  const state = useCredit();
  const { session } = useSession();
  const company = state.companies.find((c) => c.id === session?.profile);
  return (
    <>
      <HeroPanel>
        <p className="hero-eyebrow">Кредитный кабинет</p>
        <h1>{company?.name}</h1>
        <p>Заполните заявку и отслеживайте решение банка.</p>
        <Action tone="white" asChild>
          <Link to="/client/products">Подать заявку</Link>
        </Action>
      </HeroPanel>
      <Card>
        <h2>Ваши заявки</h2>
        {state.applications.length ? (
          state.applications.map((app) => (
            <div className="product-row" key={app.id}>
              <div>
                <Link
                  to={
                    app.status === 'DRAFT'
                      ? `/client/new/${app.id}`
                      : `/client/applications/${app.id}`
                  }
                >
                  № {app.id} · {products[app.product]}
                </Link>
                <p>
                  Запрошено: {requestedAmount(app)} · {requestedTerm(app)}
                </p>
              </div>
              <StatusBadge app={app} />
            </div>
          ))
        ) : (
          <p>Пока нет заявок.</p>
        )}
      </Card>
      <BusinessProducts />
    </>
  );
}
function initialFields(rows: ServerRequirement[], app: Application, company: Company) {
  const values = { ...app.fields };
  for (const r of rows) {
    if (values[r.field_code] !== undefined) continue;
    let value: unknown;
    if (r.field_number === 1) value = app.product;
    else if (r.field_number === 2)
      value = company.server?.entity_type === 'INDIVIDUAL_ENTREPRENEUR' ? 'ИП' : 'Юридическое лицо';
    else if (r.field_number === 4) value = app.purpose;
    else if (r.field_number === 5) value = app.server?.requested_amount;
    else if (r.field_number === 6) value = app.server?.requested_term_months;
    else if (r.field_number !== 31) {
      const parts = r.target_db_field
        .split(/\s*\+\s*/)
        .map((part) => {
          const [table, key] = part.split('.');
          const source =
            table === 'companies'
              ? company.server
              : table === 'application_details'
                ? app.server?.details
                : table === 'application_product_details'
                  ? app.server?.product_details
                  : undefined;
          return source?.[key];
        })
        .filter((v) => v !== undefined && v !== null);
      value = parts.length ? parts.join(' · ') : undefined;
    }
    values[r.field_code] = value === undefined || value === null ? '' : String(value);
  }
  return values;
}
export function BusinessForm() {
  const { id } = useParams();
  const state = useCredit();
  const { session } = useSession();
  const app = state.applications.find((a) => a.id === id && a.companyId === session?.profile);
  if (!app) return <EmptyState title="Заявка не найдена" />;
  if (app.status !== 'DRAFT')
    return (
      <Card>
        <Link to={`/client/applications/${app.id}`}>Заявка уже отправлена — открыть</Link>
      </Card>
    );
  const company = state.companies.find((c) => c.id === app.companyId)!;
  return (
    <DraftForm
      key={app.id}
      app={app}
      company={company}
      rows={requirements(state.requirements ?? [], app, company)}
    />
  );
}
function DraftForm({
  app,
  company,
  rows,
}: {
  app: Application;
  company: Company;
  rows: ServerRequirement[];
}) {
  const api = useApi() as HttpCreditApi;
  const nav = useNavigate();
  const action = useAction();
  const [values, setValues] = useState(() => initialFields(rows, app, company));
  const [consents, setConsents] = useState({
    consentBki: app.consentBki,
    consentData: app.consentData,
    businessConfirmed: app.businessConfirmed,
  });
  const [tranche, setTranche] = useState(
    String(app.server?.product_details?.max_tranche_term_value ?? ''),
  );
  const [unit, setUnit] = useState(
    String(app.server?.product_details?.max_tranche_term_unit ?? ''),
  );
  const [saved, setSaved] = useState(false);
  const code = (n: number) => `${app.product}_${String(n).padStart(2, '0')}`;
  const save = async () => {
    const details: Record<string, unknown> = {};
    for (const [n, key] of [
      [24, 'contact_full_name'],
      [25, 'contact_role'],
      [26, 'contact_phone'],
      [29, 'signer_full_name'],
      [30, 'signer_authority_basis'],
    ] as const) {
      if (values[code(n)]) details[key] = values[code(n)];
    }
    const product_details: Record<string, unknown> = {};
    if (app.product !== 'R01') {
      if (tranche) product_details.max_tranche_term_value = Number(tranche);
      if (unit) product_details.max_tranche_term_unit = unit;
    }
    if (app.product === 'R03')
      for (const [n, key] of [
        [32, 'overdraft_account_ref'],
        [33, 'overdraft_bank_name'],
        [34, 'overdraft_bank_bik'],
      ] as const) {
        if (values[code(n)]) product_details[key] = values[code(n)];
      }
    if (app.product === 'R02' && values[code(33)])
      product_details.drawdown_period_months = Number(values[code(33)]);
    await api.command('save', app.id, {
      patch: {
        fields: values,
        details,
        product_details,
        ...consents,
        ...(values[code(5)] ? { amount: values[code(5)] } : {}),
        ...(values[code(6)] ? { term: Number(values[code(6)]) } : {}),
        purpose: values[code(4)],
      },
    });
    setSaved(true);
  };
  return (
    <>
      <Link className="back-link" to="/client/applications">
        ← Все заявки
      </Link>
      <HeroPanel>
        <p className="hero-eyebrow">Новая заявка · {app.id}</p>
        <h1>{products[app.product]}</h1>
        <p>{company.name}</p>
      </HeroPanel>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void action.run(async () => {
            await save();
            await api.submit(app.id);
            nav(`/client/applications/${app.id}`);
          });
        }}
      >
        <Card>
          <h2>Анкета</h2>
          <p className="muted">
            Реквизиты заполнены из базы. Уточните отсутствующие сведения и параметры запроса.
          </p>
          <fieldset disabled={action.busy} className="business-fields">
            <legend className="sr-only">Поля заявки</legend>
            {rows.map((r) => {
              const value = values[r.field_code] ?? '';
              const knownCompanyFact =
                r.target_db_field.startsWith('companies.') &&
                r.target_db_field.split(/\s*\+\s*/).every((part) => {
                  const key = part.replace(/^companies\./, '');
                  return (
                    company.server?.[key] !== null &&
                    company.server?.[key] !== undefined &&
                    company.server?.[key] !== ''
                  );
                });
              const readOnly = [1, 2].includes(r.field_number) || knownCompanyFact;
              return (
                <label className="form-field" key={r.field_code}>
                  {r.field_label}
                  {r.field_number === 31 ? (
                    <span className="check-row">
                      <input
                        type="checkbox"
                        checked={value === 'Подтверждаю'}
                        onChange={(e) => {
                          setSaved(false);
                          setValues({
                            ...values,
                            [r.field_code]: e.target.checked ? 'Подтверждаю' : '',
                          });
                        }}
                      />
                      Подтверждаю корректность анкеты
                    </span>
                  ) : (
                    <Input
                      value={value}
                      readOnly={readOnly}
                      required
                      aria-label={r.field_label}
                      onChange={(e) => {
                        setSaved(false);
                        setValues({ ...values, [r.field_code]: e.target.value });
                      }}
                    />
                  )}
                  {r.format_rule && <span className="muted small">{r.format_rule}</span>}
                  {readOnly && <span className="source">Из базы</span>}
                </label>
              );
            })}
            {app.product !== 'R01' && (
              <>
                <label className="form-field">
                  Срок транша
                  <Input
                    type="number"
                    min={1}
                    value={tranche}
                    required
                    onChange={(e) => setTranche(e.target.value)}
                  />
                </label>
                <label className="form-field">
                  Единица срока транша
                  <select value={unit} required onChange={(e) => setUnit(e.target.value)}>
                    <option value="">Выберите</option>
                    <option value="DAYS">Дни</option>
                    <option value="MONTHS">Месяцы</option>
                  </select>
                </label>
              </>
            )}
          </fieldset>
        </Card>
        <Card>
          <h2>Согласия и отправка</h2>
          {(
            [
              ['businessConfirmed', 'Подтверждаю сведения о бизнесе'],
              ['consentData', 'Согласен на обработку данных'],
              ['consentBki', 'Согласен на запрос кредитной истории'],
            ] as const
          ).map(([key, label]) => (
            <label className="check-row" key={key}>
              <input
                type="checkbox"
                disabled={action.busy}
                checked={consents[key]}
                required
                onChange={(e) => setConsents({ ...consents, [key]: e.target.checked })}
              />
              {label}
            </label>
          ))}
          <ErrorState message={action.error} onRetry={action.retry} />
          {saved && <p role="status">Черновик сохранён.</p>}
          <div className="actions">
            <Action
              type="button"
              tone="outline"
              disabled={action.busy}
              onClick={() => void action.run(save)}
            >
              Сохранить черновик
            </Action>
            <Action type="submit" disabled={action.busy}>
              {action.busy ? 'Сохраняем и проверяем…' : 'Отправить заявку'}
            </Action>
          </div>
        </Card>
      </form>
      <Card>
        <Documents app={app} />
      </Card>
    </>
  );
}
function Offer({ app }: { app: Application }) {
  const offer = app.server?.offer;
  if (!offer) return null;
  return (
    <Card>
      <h2>
        {offer.offer_status === 'DRAFT'
          ? 'Рассчитанные условия — требуют решения'
          : offer.offer_status === 'ACCEPTED'
            ? 'Предложение принято'
            : 'Предложение банка'}
      </h2>
      <div className="metrics">
        <KeyValue label="Предлагаемая сумма" value={money(Number(offer.offered_amount))} />
        <KeyValue label="Срок договора" value={`${offer.offered_term_months} мес.`} />
        <KeyValue
          label="Годовая ставка"
          value={`${Number(offer.offered_annual_rate_pct).toLocaleString('ru-RU')}%`}
        />
      </div>
    </Card>
  );
}
function Reasons({ app }: { app: Application }) {
  const reasons = app.server?.reasons ?? [];
  return (
    <Card>
      <h2>Причины решения</h2>
      {app.server?.offer_stale && <p role="status">{app.server.offer_stale.reason}</p>}
      {reasons.length ? (
        reasons.map((r, i) => <p key={i}>{r.message}</p>)
      ) : (
        <p className="muted">Решение ещё не принято.</p>
      )}
    </Card>
  );
}
function RequestReply({ app, id, text }: { app: Application; id: string; text: string }) {
  const api = useApi();
  const action = useAction();
  const [answer, setAnswer] = useState('');
  return (
    <Card>
      <h2>Нужно уточнение</h2>
      <p>{text}</p>
      <Documents app={app} requestId={id} />
      <label className="form-field">
        Ваш ответ
        <Textarea value={answer} onChange={(e) => setAnswer(e.target.value)} />
      </label>
      <ErrorState message={action.error} />
      <Action
        disabled={action.busy || !answer.trim()}
        onClick={() => void action.run(() => api.answerRequest(app.id, id, answer))}
      >
        Отправить ответ
      </Action>
    </Card>
  );
}
function Documents({ app, requestId }: { app: Application; requestId?: string }) {
  const api = useApi() as HttpCreditApi;
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const documents = (app.server?.documents ?? []).filter(
    (document) => !requestId || String(document.data_request_id) === requestId,
  );
  return (
    <section aria-label={requestId ? 'Документы дозапроса' : 'Документы заявки'}>
      <h2>{requestId ? 'Документы дозапроса' : 'Документы заявки'}</h2>
      <p className="small muted">
        PDF или CSV в UTF-8, до 10 МиБ. Загрузка сохраняет документ без проверки содержания.
        Дозапрос закрывается только после отправки ответа.
      </p>
      {documents.map((document) => (
        <div className="inset" key={document.document_id}>
          <a href={`/api/v2/documents/${document.document_id}`} download>
            {document.filename}
          </a>
          <p className="small muted">
            {document.size.toLocaleString('ru-RU')} байт · Сохранён, не проверен ·{' '}
            {document.source === 'CLIENT_UPLOAD' ? 'Загружен клиентом' : 'Загружен сотрудником'} (ID{' '}
            {document.uploaded_by})
            {document.data_request_id ? ` · Дозапрос № ${document.data_request_id}` : ''}
          </p>
        </div>
      ))}
      {!documents.length && <p className="muted">Документов пока нет.</p>}
      <label className="form-field">
        Выбрать PDF или CSV
        <input
          type="file"
          accept=".pdf,.csv"
          disabled={action.busy}
          onChange={(event) => setFile(event.target.files?.[0] ?? null)}
        />
      </label>
      <ErrorState message={action.error} onRetry={action.retry} />
      <Action
        disabled={action.busy || !file}
        onClick={() =>
          void action.run(async () => {
            if (file) await api.uploadDocument(app.id, file, requestId);
          })
        }
      >
        {action.busy ? 'Сохранение документа…' : 'Загрузить документ'}
      </Action>
    </section>
  );
}
export function BusinessDetail() {
  const { id } = useParams();
  const state = useCredit();
  const { session } = useSession();
  const api = useApi();
  const action = useAction();
  const app = state.applications.find((a) => a.id === id && a.companyId === session?.profile);
  if (!app) return <EmptyState title="Заявка не найдена" />;
  return (
    <>
      <Link className="back-link" to="/client/applications">
        ← Все заявки
      </Link>
      <HeroPanel>
        <StatusBadge app={app} />
        <h1>{products[app.product]}</h1>
        <p>
          Запрошено: {requestedAmount(app)} · {requestedTerm(app)}
        </p>
        <p>Цель: {app.purpose || 'Не указана'}</p>
      </HeroPanel>
      {app.status === 'DRAFT' && (
        <Card>
          <Link to={`/client/new/${app.id}`}>Продолжить заполнение</Link>
        </Card>
      )}
      <Offer app={app} />
      <Reasons app={app} />
      <Card>
        <Documents app={app} />
      </Card>
      {app.requests
        .filter((r) => r.state === 'OPEN')
        .map((r) => (
          <RequestReply key={r.id} app={app} id={r.id} text={r.text} />
        ))}
      <Card>
        <ErrorState message={action.error} onRetry={action.retry} />
        <div className="actions">
          {app.status === 'APPROVED' && app.offerStatus === 'PROPOSED' && (
            <Action
              disabled={action.busy}
              onClick={() => void action.run(() => api.accept(app.id, app.offers[0].id))}
            >
              Принять предложение
            </Action>
          )}
          {!['REJECTED', 'CANCELLED'].includes(app.status) && app.offerStatus !== 'ACCEPTED' && (
            <Action
              tone="outline"
              disabled={action.busy}
              onClick={() => void action.run(() => api.cancel(app.id))}
            >
              {app.offerStatus === 'PROPOSED' ? 'Отклонить и отменить заявку' : 'Отменить заявку'}
            </Action>
          )}
          {app.offerStatus === 'ACCEPTED' && <p role="status">Условия приняты и сохранены.</p>}
        </div>
      </Card>
    </>
  );
}
export function BusinessQueue({ mine = false }: { mine?: boolean }) {
  const state = useCredit();
  const { session } = useSession();
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const apps = state.applications.filter(
    (a) =>
      a.status !== 'DRAFT' &&
      (!mine || String(a.server?.assignment?.employee_id) === session?.userId) &&
      `${a.id} ${state.companies.find((c) => c.id === a.companyId)?.name}`
        .toLowerCase()
        .includes(query.toLowerCase()) &&
      (filter === 'all' || a.status === filter),
  );
  return (
    <>
      <HeroPanel>
        <p className="hero-eyebrow">Кабинет сотрудника</p>
        <h1>{mine ? 'Мои разборы' : 'Очередь заявок'}</h1>
        <p>Данные заявок и решений из базы.</p>
      </HeroPanel>
      <Card>
        <label className="form-field">
          Найти заявку
          <Input value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <label className="form-field">
          Статус
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">Все</option>
            <option value="UNDER_REVIEW">На рассмотрении</option>
            <option value="AWAITING_DATA">Нужны данные</option>
            <option value="APPROVED">Одобрено</option>
            <option value="REJECTED">Отказ</option>
            <option value="CANCELLED">Отменена</option>
          </select>
        </label>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Заявка / компания</th>
                <th>Продукт</th>
                <th>Запрошено</th>
                <th>Статус</th>
                <th>Ответственный</th>
              </tr>
            </thead>
            <tbody>
              {apps.map((app) => (
                <tr key={app.id}>
                  <td>
                    <Link to={`/bank/applications/${app.id}`}>
                      № {app.id} · {state.companies.find((c) => c.id === app.companyId)?.name}
                    </Link>
                  </td>
                  <td>{products[app.product]}</td>
                  <td>
                    {requestedAmount(app)} · {requestedTerm(app)}
                  </td>
                  <td>
                    <StatusBadge app={app} />
                  </td>
                  <td>
                    <Responsible app={app} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!apps.length && <p>Нет заявок по выбранному фильтру.</p>}
      </Card>
    </>
  );
}
export function BusinessReview() {
  const { id } = useParams();
  const state = useCredit();
  const app = state.applications.find((a) => a.id === id);
  if (!app) return <EmptyState title="Заявка не найдена" />;
  return <ReviewDetails key={`${app.id}-${app.revision}`} app={app} />;
}
function ReviewDetails({ app }: { app: Application }) {
  const api = useApi() as HttpCreditApi;
  const state = useCredit();
  const action = useAction();
  const { session } = useSession();
  const assignedToMe = String(app.server?.assignment?.employee_id) === session?.userId;
  const [reason, setReason] = useState('');
  const [decision, setDecision] = useState('APPROVE');
  const [field, setField] = useState('');
  const [checkKind, setCheckKind] = useState<'authority' | 'revenue'>('authority');
  const [checkSource, setCheckSource] = useState('');
  const [checkComment, setCheckComment] = useState('');
  const risk = app.server?.assessment?.risk_assessment;
  const pd = (n?: number | null) =>
    n === undefined || n === null
      ? 'Нет данных'
      : `${(n * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`;
  const active = ['UNDER_REVIEW', 'SUBMITTED', 'AWAITING_DATA'].includes(app.status);
  const editable = active && assignedToMe;
  return (
    <>
      <Link className="back-link" to="/bank">
        ← Очередь
      </Link>
      <HeroPanel>
        <StatusBadge app={app} />
        <h1>{state.companies.find((c) => c.id === app.companyId)?.name}</h1>
        <p>
          {products[app.product]} · запрошено {requestedAmount(app)} · {requestedTerm(app)}
        </p>
        <p>Цель: {app.purpose || 'Не указана'}</p>
      </HeroPanel>
      <Card>
        <h2>Ответственный</h2>
        <Responsible app={app} />
        <ErrorState message={action.error} onRetry={action.retry} />
        {active && !app.server?.assignment && (
          <Action
            disabled={action.busy}
            onClick={() => void action.run(() => api.command('claim', app.id))}
          >
            Взять в работу
          </Action>
        )}
        {assignedToMe && (
          <Action
            tone="outline"
            disabled={action.busy}
            onClick={() => void action.run(() => api.command('release', app.id))}
          >
            Освободить заявку
          </Action>
        )}
        {active && !editable && (
          <p className="muted">Проверку, скоринг и решение сохраняет ответственный сотрудник.</p>
        )}
      </Card>
      <div className="two-columns">
        <Card>
          <h2>Оценка заявки</h2>
          <div className="metrics">
            <KeyValue label="PD за 12 месяцев" value={pd(risk?.pd_application_1y)} />
            <KeyValue label="Допустимый годовой лимит PD" value={pd(risk?.pd_limit_1y)} />
          </div>
        </Card>
        <Offer app={app} />
      </div>
      <Reasons app={app} />
      <Card>
        <Documents app={app} />
      </Card>
      <Card>
        <h2>Анкета клиента</h2>
        <dl className="details">
          {app.server?.fields.map((f) => (
            <div key={f.field_code}>
              <dt>
                {state.requirements?.find((r) => r.field_code === f.field_code)?.field_label ??
                  f.field_code}
              </dt>
              <dd>
                {String(f.field_value ?? 'Нет данных')}{' '}
                <span className="source">{f.verification_status}</span>
              </dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card>
        <h2>Проверки сотрудника</h2>
        {app.server?.verifications?.map((check, index) => (
          <div className="inset" key={index}>
            <h3>
              {check.details.kind === 'authority' ? 'Полномочия подписанта' : 'Расхождение выручки'}
            </h3>
            <p>{check.details.comment}</p>
            <p className="small muted">
              Источник: {check.details.source_ref} · {check.first_name} {check.last_name} ·{' '}
              {new Date(check.created_at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })}
            </p>
          </div>
        ))}
        {editable && (
          <>
            <label className="form-field">
              Вид проверки
              <select
                value={checkKind}
                onChange={(e) => setCheckKind(e.target.value as 'authority' | 'revenue')}
              >
                <option value="authority">Полномочия подписанта</option>
                <option value="revenue">Расхождение выручки</option>
              </select>
            </label>
            <label className="form-field">
              Документ или источник
              <Input value={checkSource} onChange={(e) => setCheckSource(e.target.value)} />
            </label>
            <label className="form-field">
              Результат проверки
              <Textarea value={checkComment} onChange={(e) => setCheckComment(e.target.value)} />
            </label>
            <ErrorState message={action.error} />
            <Action
              disabled={action.busy || !checkSource.trim() || !checkComment.trim()}
              onClick={() =>
                void action.run(() => api.resolveData(app.id, checkKind, checkComment, checkSource))
              }
            >
              Зафиксировать проверку
            </Action>
          </>
        )}
      </Card>
      {editable && (
        <Card>
          <h2>Решение сотрудника</h2>
          <ErrorState message={action.error} onRetry={action.retry} />
          <label className="form-field">
            Решение
            <select
              value={decision}
              disabled={action.busy}
              onChange={(e) => setDecision(e.target.value)}
            >
              <option value="APPROVE" disabled={!app.server?.offer || app.offerStatus !== 'DRAFT'}>
                Одобрить рассчитанные условия
              </option>
              <option value="REJECT">Отказать</option>
              <option value="REQUEST_DATA">Запросить данные</option>
            </select>
          </label>
          {decision === 'REQUEST_DATA' && (
            <label className="form-field">
              Какое поле уточнить
              <select value={field} onChange={(e) => setField(e.target.value)}>
                <option value="">Выберите поле</option>
                {state.requirements
                  ?.filter((r) => r.product_code === app.product)
                  .map((r) => (
                    <option key={r.field_code} value={r.field_code}>
                      {r.field_label}
                    </option>
                  ))}
              </select>
            </label>
          )}
          <label className="form-field">
            Причина, которую увидит клиент
            <Textarea value={reason} onChange={(e) => setReason(e.target.value)} />
          </label>
          <div className="actions">
            <Action
              disabled={
                action.busy ||
                !reason.trim() ||
                (decision === 'APPROVE' && (!app.server?.offer || app.offerStatus !== 'DRAFT')) ||
                (decision === 'REQUEST_DATA' && !field)
              }
              onClick={() =>
                void action.run(() =>
                  api.command('review', app.id, { decision, reason, field_code: field }),
                )
              }
            >
              Сохранить решение
            </Action>
            {app.status !== 'AWAITING_DATA' && (
              <Action
                tone="outline"
                disabled={action.busy}
                onClick={() => void action.run(() => api.command('score', app.id))}
              >
                Повторить скоринг
              </Action>
            )}
          </div>
        </Card>
      )}
    </>
  );
}
function Responsible({ app }: { app: Application }) {
  const assigned = app.server?.assignment;
  return (
    <p>
      {assigned
        ? `${assigned.first_name} ${assigned.last_name} (ID ${assigned.employee_id})`
        : 'Не назначен'}
    </p>
  );
}
