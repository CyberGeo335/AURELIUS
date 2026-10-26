import { DraftForm } from './BusinessFormSteps';
import { HttpBankQueue } from './HttpBankQueue';
import { clientVisibleReasons } from '../domain/clientReasons';
import { HttpProvenance } from './HttpProvenance';
import { AssistantDraftCard } from './HttpAssistant';
import { ProductTerms } from './ProductTerms';
import { HttpBankHistory, HttpClientJourney } from './HttpHistory';
import type { ReactNode } from 'react';
import { ClientHome } from './ClientHome';
import { useRef, useState } from 'react';
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
  StageTrack,
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
      r.product_code === app.product &&
      (company.server?.entity_type === 'INDIVIDUAL_ENTREPRENEUR' ? r.required_ip : r.required_ooo),
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
              <ProductTerms row={row} />
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
  return (
    <ClientHome>
      <BusinessProducts />
    </ClientHome>
  );
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
  if (!['INDIVIDUAL_ENTREPRENEUR', 'LEGAL_ENTITY'].includes(String(company.server?.entity_type)))
    return <EmptyState title="Не указан тип заявителя" />;
  return (
    <DraftForm
      key={app.id}
      app={app}
      company={company}
      rows={requirements(state.requirements ?? [], app, company)}
    >
      <Card>
        <Documents app={app} />
      </Card>
    </DraftForm>
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
function Reasons({ app, audience = 'client' }: { app: Application; audience?: 'client' | 'bank' }) {
  const allReasons = app.server?.reasons ?? [];
  const reasons = audience === 'client' ? clientVisibleReasons(allReasons) : allReasons;
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
function RequestPresentation({
  text,
  fieldLabel,
  children,
}: {
  text: string;
  fieldLabel?: string;
  children?: ReactNode;
}) {
  return (
    <Card>
      <h2>Нужно уточнение</h2>
      <p>{text}</p>
      {fieldLabel && <p className="small muted">Поле: {fieldLabel}</p>}
      {children}
    </Card>
  );
}
function DecisionPreview({
  app,
  decision,
  reason,
  field,
  fieldLabel,
}: {
  app: Application;
  decision: string;
  reason: string;
  field: string;
  fieldLabel?: string;
}) {
  const text = reason.trim();
  const preview = {
    ...app,
    server: app.server
      ? {
          ...app.server,
          offer_stale: null,
          reasons: text ? [{ code: `BANK_${decision}`, message: text }] : [],
          offer: app.server.offer?.offer_status === 'DRAFT'
            ? { ...app.server.offer, offer_status: 'PROPOSED' as const }
            : null,
        }
      : undefined,
  };
  return (
    <section className="decision-preview" aria-label="Клиент увидит">
      <h3>Клиент увидит</h3>
      <p className="small muted">Предпросмотр после сохранения решения.</p>
      {!text ? (
        <p>Введите причину для предпросмотра.</p>
      ) : (
        <>
          {decision === 'APPROVE' &&
            (preview.server?.offer ? (
              <Offer app={preview} />
            ) : (
              <p>Нет рассчитанного предложения.</p>
            ))}
          {decision === 'REJECT' && (
            <p>
              <strong>Отказ</strong>
            </p>
          )}
          {decision === 'REQUEST_DATA' && (
            <RequestPresentation
              text={text}
              fieldLabel={field ? (fieldLabel ?? field) : 'Выберите поле'}
            />
          )}
          <Reasons app={preview} />
        </>
      )}
    </section>
  );
}
function RequestReply({ app, id, text }: { app: Application; id: string; text: string }) {
  const api = useApi();
  const action = useAction();
  const [answer, setAnswer] = useState('');
  const state = useCredit();
  const field = app.server?.requests.find((r) => String(r.request_id) === id)?.field_code;
  const fieldLabel =
    state.requirements?.find((r) => r.product_code === app.product && r.field_code === field)
      ?.field_label ?? field;
  return (
    <RequestPresentation text={text} fieldLabel={fieldLabel}>
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
    </RequestPresentation>
  );
}
function Documents({ app, requestId }: { app: Application; requestId?: string }) {
  const api = useApi() as HttpCreditApi;
  const action = useAction();
  const [file, setFile] = useState<File | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
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
          ref={fileInput}
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
            if (file) {
              await api.uploadDocument(app.id, file, requestId);
              setFile(null);
              if (fileInput.current) fileInput.current.value = '';
            }
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
        <StageTrack app={app} />
      </HeroPanel>
      {app.status === 'DRAFT' && (
        <Card>
          <Link to={`/client/new/${app.id}`}>Продолжить заполнение</Link>
        </Card>
      )}
      {app.status === 'DRAFT' && <AssistantDraftCard app={app} />}
      <HttpClientJourney app={app} />
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
  return <HttpBankQueue mine={mine} />;
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
      <StageTrack app={app} bank />
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
      <Reasons app={app} audience="bank" />
      <Card>
        <Documents app={app} />
      </Card>
      <HttpProvenance
        app={app}
        company={state.companies.find((c) => c.id === app.companyId)}
        requirements={state.requirements ?? []}
      />
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
          <DecisionPreview
            app={app}
            decision={decision}
            reason={reason}
            field={field}
            fieldLabel={
              state.requirements?.find(
                (r) => r.product_code === app.product && r.field_code === field,
              )?.field_label
            }
          />
        </Card>
      )}
      <HttpBankHistory applications={[app]} single />
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
