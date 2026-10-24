import { useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { Search } from 'lucide-react';
import { useCredit } from '../../app/context';
import {
  Action,
  Card,
  HeroPanel,
  StageTrack,
  StatusBadge,
  EmptyState,
  KeyValue,
} from '../../components/v2/primitives';
import { Input } from '../../components/ui/input';
import { coverage, decimal, money, date } from '../../domain/finance';
import { products } from '../../domain/types';
import { demoRisk } from '../../domain/risk';
export function Queue({ mine = false }: { mine?: boolean }) {
  const state = useCredit();
  const [filter, setFilter] = useState('all');
  const [query, setQuery] = useState('');
  const nav = useNavigate();
  const apps = state.applications.filter(
    (a) => a.status !== 'DRAFT' && (!mine || a.owner === 'Анна Смирнова'),
  );
  const manual = apps.filter((a) => a.status === 'MANUAL_REVIEW');
  const groups = [
    ['all', 'Все'],
    ['manual', 'Ручной разбор'],
    ['info', 'Ждут клиента'],
    ['checking', 'Проверка идёт'],
    ['done', 'Решены'],
  ];
  const match = (status: string, key: string) =>
    key === 'all' ||
    (key === 'manual'
      ? status === 'MANUAL_REVIEW'
      : key === 'info'
        ? status === 'NEEDS_INFO'
        : key === 'checking'
          ? ['SUBMITTED', 'CHECKING'].includes(status)
          : ['OFFERED', 'ACCEPTED', 'SIGNED_DEMO', 'FUNDED_DEMO', 'DECLINED', 'CANCELLED'].includes(
              status,
            ));
  const visible = apps
    .filter(
      (a) =>
        match(a.status, filter) &&
        `${a.id} ${state.companies.find((c) => c.id === a.companyId)?.name}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    )
    .sort((a, b) => a.updated - b.updated);
  const automatic = apps.filter((a) =>
    a.history.some((e) => e.text.startsWith('Подготовили предложение')),
  ).length;
  const durations = apps.flatMap((a) => {
    const event = a.history.find(
      (e) =>
        e.text.startsWith('Подготовили предложение') ||
        e.text.startsWith('Встречное предложение') ||
        e.text.startsWith('Отказ'),
    );
    return event ? [Math.max(1, Math.round((event.at - a.created) / 60000))] : [];
  });
  const average = durations.length
    ? Math.round(durations.reduce((n, v) => n + v, 0) / durations.length)
    : 0;
  return (
    <>
      <div className="queue-hero">
        <HeroPanel symbol={String(manual.length)}>
          <p className="hero-eyebrow">Ручной разбор</p>
          <h1>
            {manual.length} {manual.length === 1 ? 'заявка ждёт' : 'заявки ждут'} вашего решения
          </h1>
          <p>
            Автоматика остановилась и объяснила почему: нагрузка на бизнес, расхождение данных или
            неподтверждённые полномочия.
          </p>
          <div className="actions">
            <Action
              tone="white"
              disabled={!manual.length}
              onClick={() =>
                nav('/bank/applications/' + [...manual].sort((a, b) => a.updated - b.updated)[0].id)
              }
            >
              Взять самую старую
            </Action>
            <Action tone="outline" onClick={() => setFilter('manual')}>
              Показать только ручные
            </Action>
          </div>
        </HeroPanel>
        <Card className="dark">
          <p className="muted">Сегодня, {date(Date.now())} · демо-сводка</p>
          <div className="daily-stats">
            <KeyValue label="заявок в демо-очереди" value={apps.length} />
            <KeyValue
              label={`решено автоматически, ${apps.length ? Math.round((automatic / apps.length) * 100) : 0}%`}
              value={automatic}
            />
            <KeyValue
              label="ждут ответа клиента"
              value={apps.filter((a) => a.status === 'NEEDS_INFO').length}
            />
            <KeyValue
              label="в среднем до решения"
              value={durations.length ? `${average} мин` : 'Пока нет решений'}
            />
          </div>
        </Card>
      </div>
      <Card className="queue-card">
        <div className="spread">
          <h2>{mine ? 'Мои разборы' : 'Очередь'}</h2>
          <div className="filters" aria-label="Фильтр статуса">
            {groups.map(([key, label]) => (
              <button key={key} aria-pressed={filter === key} onClick={() => setFilter(key)}>
                {label} <span>{apps.filter((a) => match(a.status, key)).length}</span>
              </button>
            ))}
          </div>
        </div>
        <label className="search-field">
          <Search aria-hidden size={18} />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Клиент или номер заявки"
            aria-label="Поиск заявки"
          />
        </label>
        {visible.length ? (
          <div className="table-scroll">
            <table className="queue-table">
              <thead>
                <tr>
                  <th>Заявка и клиент</th>
                  <th>Продукт и сумма</th>
                  <th>Этап</th>
                  <th>Риск</th>
                  <th>Покрытие</th>
                  <th>Что требует внимания</th>
                  <th>Ждёт</th>
                  <th>
                    <span className="sr-only">Действие</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {visible.map((a) => {
                  const c = state.companies.find((c) => c.id === a.companyId)!;
                  const evaluated = [
                    'MANUAL_REVIEW',
                    'OFFERED',
                    'ACCEPTED',
                    'SIGNED_DEMO',
                    'FUNDED_DEMO',
                  ].includes(a.status);
                  const ratio = coverage(a.flow, a.existing, a.amount, a.term);
                  return (
                    <tr className={a.status === 'MANUAL_REVIEW' ? 'attention-row' : ''} key={a.id}>
                      <td>
                        <strong>{c.name}</strong>
                        <span className="small muted block">{a.id}</span>
                      </td>
                      <td>
                        {products[a.product]}
                        <span className="small muted block">
                          {money(a.amount)} · {a.term} мес.
                        </span>
                      </td>
                      <td>
                        <StageTrack app={a} bank mini />
                        <span className="small muted">
                          {a.status === 'MANUAL_REVIEW'
                            ? 'Политика'
                            : a.status === 'NEEDS_INFO'
                              ? 'Дозапрос'
                              : a.status === 'CHECKING'
                                ? 'Проверка'
                                : 'Решение'}
                        </span>
                      </td>
                      <td>
                        {evaluated ? (
                          <span className={`status ${demoRisk(a).tone}`}>{demoRisk(a).label}</span>
                        ) : (
                          <span className="small muted">Нет оценки</span>
                        )}
                      </td>
                      <td>
                        <strong className={ratio < 1.3 ? 'red-text' : ''}>
                          {evaluated ? `${decimal(ratio)}×` : '—'}
                        </strong>
                      </td>
                      <td>
                        {a.reason ||
                          a.requests.find((r) => r.state === 'OPEN')?.text ||
                          'Проверка по демо-условиям'}
                      </td>
                      <td className="nowrap">
                        {Math.max(1, Math.floor((Date.now() - a.updated) / 60000))} мин
                      </td>
                      <td>
                        <Action tone={a.status === 'MANUAL_REVIEW' ? 'red' : 'soft'} asChild>
                          <Link to={`/bank/applications/${a.id}`}>
                            {a.status === 'MANUAL_REVIEW' ? 'Разобрать' : 'Открыть'}
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
          <EmptyState title="По этому фильтру заявок нет">
            <p>Измените статус или поисковый запрос.</p>
          </EmptyState>
        )}
      </Card>
    </>
  );
}
export function BankJournal() {
  const state = useCredit();
  const rows = state.applications
    .flatMap((app) => app.history.map((event) => ({ app, event })))
    .sort((a, b) => b.event.at - a.event.at);
  return (
    <>
      <h1>Журнал действий</h1>
      <Card>
        <table>
          <thead>
            <tr>
              <th>Когда</th>
              <th>Заявка</th>
              <th>Кто и что</th>
              <th>Основание</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ app, event }) => (
              <tr key={event.id}>
                <td>{new Date(event.at).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })}</td>
                <td>
                  <Link to={`/bank/applications/${app.id}`}>{app.id}</Link>
                  <br />
                  <StatusBadge app={app} />
                </td>
                <td>
                  <strong>{event.actor}</strong>
                  <p>{event.text}</p>
                </td>
                <td className="small">
                  Ревизия {event.revision}
                  <br />
                  {event.model}
                  <br />
                  {event.policy}
                  <br />
                  {event.snapshot}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </>
  );
}
