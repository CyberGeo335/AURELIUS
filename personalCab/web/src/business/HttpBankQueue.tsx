import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Search } from 'lucide-react';
import { useCredit, useSession } from '../app/context';
import {
  Action,
  Card,
  HeroPanel,
  KeyValue,
  StageTrack,
  StatusBadge,
} from '../components/v2/primitives';
import { Input } from '../components/ui/input';
import {
  awaitsDecision,
  durationLabel,
  firstDecisionAverage,
  lastQueueEvent,
  needsClientData,
  oldestFirst,
  openRequests,
  queueFilters,
  queueMatches,
  type QueueFilter,
} from '../domain/httpQueue';
import { money } from '../domain/finance';
import { counted } from '../domain/text';
import { products, type Application } from '../domain/types';

const validPd = (n: unknown): n is number =>
  typeof n === 'number' && Number.isFinite(n) && n >= 0 && n <= 1;
const percent = (n: number) =>
  `${(n * 100).toLocaleString('ru-RU', { maximumFractionDigits: 2 })}%`;
function QueuePd({ app }: { app: Application }) {
  const risk = app.server?.assessment?.risk_assessment;
  if (!validPd(risk?.pd_application_1y)) return <span className="muted">Нет оценки</span>;
  const pd = risk.pd_application_1y;
  const limit = risk.pd_limit_1y;
  return (
    <>
      <strong>{percent(pd)}</strong>
      <span className="small block">
        {validPd(limit)
          ? `${pd <= limit ? 'В лимите' : 'Выше лимита'} · ${percent(limit)}`
          : 'Лимит не указан'}
      </span>
      {app.server?.offer_stale && <span className="small muted block">Предыдущая оценка</span>}
    </>
  );
}
function QueueAttention({ app }: { app: Application }) {
  const count = openRequests(app);
  const conflicts =
    app.server?.fields.filter((f) => f.verification_status === 'CONFLICT').length ?? 0;
  const stale = app.server?.offer_stale;
  const reasons = app.server?.reasons ?? [];
  if (!count && !conflicts && !stale && !reasons.length) return <>—</>;
  return (
    <div className="http-queue-attention">
      {count > 0 && <p>Открыто: {counted(count, ['запрос', 'запроса', 'запросов'])}</p>}
      {conflicts > 0 && (
        <p>{counted(conflicts, ['конфликт', 'конфликта', 'конфликтов'])} в полях</p>
      )}
      {stale && <p>Устаревшее предложение{stale.reason ? `: ${stale.reason}` : ''}</p>}
      {reasons.map((r, i) => (
        <p key={i}>
          <span className="small muted block">{r.code}</span>
          {r.message}
        </p>
      ))}
    </div>
  );
}
export function HttpBankQueue({ mine = false }: { mine?: boolean }) {
  const state = useCredit();
  const { session } = useSession();
  const [filter, setFilter] = useState<QueueFilter>('all');
  const [query, setQuery] = useState('');
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60000);
    return () => clearInterval(timer);
  }, []);
  const applications = state.applications
    .filter(
      (a) =>
        a.status !== 'DRAFT' &&
        (!mine || String(a.server?.assignment?.employee_id) === session?.userId),
    )
    .sort(oldestFirst);
  const waiting = applications.filter(awaitsDecision);
  const average = firstDecisionAverage(applications);
  const visible = applications.filter(
    (a) =>
      queueMatches(a, filter) &&
      `${a.id} ${state.companies.find((c) => c.id === a.companyId)?.name ?? ''}`
        .toLocaleLowerCase('ru-RU')
        .includes(query.trim().toLocaleLowerCase('ru-RU')),
  );
  return (
    <div className="http-queue">
      <div className="queue-hero">
        <HeroPanel symbol={String(waiting.length)}>
          <p className="hero-eyebrow">{mine ? 'Мои разборы' : 'Кабинет сотрудника'}</p>
          <h1>
            {counted(waiting.length, ['заявка', 'заявки', 'заявок'])}{' '}
            {waiting.length === 1 ? 'ждёт' : 'ждут'} вашего решения
          </h1>
          <p>Оценка получена, открытых запросов нет. Решение принимает сотрудник банка.</p>
          <div className="actions">
            {waiting.length ? (
              <Action tone="white" asChild>
                <Link to={`/bank/applications/${waiting[0].id}`}>Разобрать первую</Link>
              </Action>
            ) : (
              <Action tone="white" disabled>
                Разобрать первую
              </Action>
            )}
            <Action tone="outline" onClick={() => setFilter('decision')}>
              Показать ждущие решения
            </Action>
          </div>
        </HeroPanel>
        <Card className="dark">
          <p className="muted">
            {mine ? 'Сводка по вашим заявкам' : 'Сводка очереди'} · данные кабинета
          </p>
          <div className="daily-stats">
            <KeyValue label="заявок в очереди" value={applications.length} />
            <KeyValue label="ждут решения" value={waiting.length} />
            <KeyValue
              label="ждут ответа клиента"
              value={applications.filter(needsClientData).length}
            />
            <KeyValue
              label="в среднем до первого решения сотрудника"
              value={average == null ? 'Пока нет решений' : durationLabel(average)}
            />
          </div>
        </Card>
      </div>
      <Card className="queue-card">
        <div className="spread">
          <h2>{mine ? 'Мои разборы' : 'Очередь'}</h2>
          <div className="filters" aria-label="Фильтр статуса">
            {queueFilters.map(([key, label]) => (
              <button
                key={key}
                type="button"
                aria-pressed={filter === key}
                onClick={() => setFilter(key)}
              >
                {label} <span>{applications.filter((a) => queueMatches(a, key)).length}</span>
              </button>
            ))}
          </div>
        </div>
        <label className="search-field">
          <Search aria-hidden size={18} />
          <Input
            aria-label="Поиск заявки"
            placeholder="Клиент или номер заявки"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        {visible.length ? (
          <div className="table-scroll">
            <table className="queue-table" aria-label="Заявки банка">
              <thead>
                <tr>
                  {[
                    'Заявка и клиент',
                    'Продукт и сумма',
                    'Этап',
                    'PD 12 мес.',
                    'Что требует внимания',
                    'Ждёт',
                    'Ответственный',
                    'Действие',
                  ].map((label) => (
                    <th key={label}>{label}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {visible.map((app) => {
                  const assignment = app.server?.assignment;
                  const last = lastQueueEvent(app);
                  return (
                    <tr key={app.id} className={awaitsDecision(app) ? 'attention-row' : undefined}>
                      <td>
                        <Link to={`/bank/applications/${app.id}`}>
                          <strong>
                            {state.companies.find((c) => c.id === app.companyId)?.name ??
                              'Компания не указана'}
                          </strong>
                          <span className="small muted block">№ {app.id}</span>
                        </Link>
                      </td>
                      <td>
                        {products[app.product]}
                        <span className="small muted block">
                          {app.server?.requested_amount == null ||
                          !app.server.requested_amount.trim()
                            ? 'Сумма не указана'
                            : money(Number(app.server.requested_amount))}{' '}
                          ·{' '}
                          {app.server?.requested_term_months == null
                            ? 'Срок не указан'
                            : `${app.server.requested_term_months} мес.`}
                        </span>
                      </td>
                      <td>
                        <StatusBadge app={app} />
                        <StageTrack app={app} bank mini />
                      </td>
                      <td>
                        <QueuePd app={app} />
                      </td>
                      <td>
                        <QueueAttention app={app} />
                      </td>
                      <td>
                        <span title="С последнего события, иначе — с даты создания заявки">
                          {durationLabel(last == null ? undefined : now - last)}
                        </span>
                      </td>
                      <td>
                        {assignment
                          ? `${assignment.first_name} ${assignment.last_name} (ID ${assignment.employee_id})`
                          : 'Не назначен'}
                      </td>
                      <td>
                        <Action asChild tone={awaitsDecision(app) ? 'red' : 'ghost'}>
                          <Link to={`/bank/applications/${app.id}`}>
                            {awaitsDecision(app) ? 'Разобрать' : 'Открыть'}
                          </Link>
                        </Action>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <p>Нет заявок по выбранному фильтру.</p>
        )}
      </Card>
    </div>
  );
}
