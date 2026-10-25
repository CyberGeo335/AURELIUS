import { displayStatus } from '../../domain/status';
import { useId, type ReactNode, type ComponentProps } from 'react';
import { motion, useReducedMotion } from 'motion/react';
import { ArrowRight, Check, MessageCircle, AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';
import type { Application, Company } from '../../domain/types';
import { statusLabels } from '../../domain/status';
import { decimal, datetime, money, MIN_COVERAGE } from '../../domain/finance';
import { applicableFields } from '../../domain/forms';
export function Action({
  tone = 'red',
  className = '',
  ...props
}: ComponentProps<typeof Button> & {
  tone?: 'red' | 'ink' | 'white' | 'soft' | 'outline' | 'ghost';
}) {
  return <Button {...props} className={`action action-${tone} ${className}`} />;
}
export function Card({ children, className = '', ...props }: ComponentProps<'section'>) {
  return (
    <section {...props} className={`card ${className}`}>
      {children}
    </section>
  );
}
export function SourceBadge({ children }: { children: ReactNode }) {
  return <span className="source">{children}</span>;
}
export function StatusBadge({ app }: { app: Application }) {
  return (
    <span
      className={`status status-${displayStatus(app) === 'OFFERED' && app.offers[0]?.kind === 'COUNTEROFFER' ? 'NEEDS_INFO' : displayStatus(app)}`}
    >
      {displayStatus(app) === 'OFFERED' && app.offers[0]?.kind === 'COUNTEROFFER'
        ? 'Одобрено на других условиях'
        : statusLabels[displayStatus(app)]}
    </span>
  );
}
export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return message ? (
    <div className="error-box" role="alert">
      <AlertCircle aria-hidden size={20} />
      <span>{message}</span>
      {onRetry && (
        <button className="quiet-button" onClick={onRetry}>
          Повторить
        </button>
      )}
    </div>
  ) : null;
}
export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Card className="empty">
      <h2>{title}</h2>
      {children}
    </Card>
  );
}
export function StageTrack({
  app,
  bank = false,
  mini = false,
}: {
  app: Application;
  bank?: boolean;
  mini?: boolean;
}) {
  const reduced = useReducedMotion();
  const trackId = useId();
  const labels = bank
    ? ['Приём', 'Проверка данных', 'Обогащение', 'Скоринг', 'Политика', 'Решение']
    : ['Отправлена', 'Данные подтверждены', 'Кредитная история', 'Оценка риска', 'Решение'];
  const current = Math.min(labels.length - 1, app.stage);
  return (
    <ol
      aria-label="Этапы обработки"
      className={`stage-track ${mini ? 'mini' : ''}`}
      style={{ gridTemplateColumns: `repeat(${labels.length}, minmax(0, 1fr))` }}
    >
      {labels.map((label, i) => (
        <motion.li
          layout={!reduced}
          initial={reduced || mini ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{
            type: 'spring',
            bounce: 0,
            duration: 0.35,
            opacity: { delay: mini ? 0 : i * 0.04 },
          }}
          key={label}
          aria-current={i === current ? 'step' : undefined}
          className={`chevron ${i < current ? 'done' : i === current ? 'current' : 'future'}`}
        >
          {i === current && !mini && (
            <motion.span
              aria-hidden
              className="stage-marker"
              layoutId={reduced ? undefined : `${trackId}-current`}
              transition={{ type: 'spring', bounce: 0, duration: 0.35 }}
            />
          )}
          <span className={mini ? 'sr-only' : 'stage-label'}>
            {label}
            {bank && i === current && displayStatus(app) === 'MANUAL_REVIEW' ? ' · стоп' : ''}
          </span>
        </motion.li>
      ))}
      {!mini && (
        <li className="sr-only" aria-live="polite" aria-atomic="true">
          Текущий этап: {labels[current]}. {statusLabels[displayStatus(app)]}.
        </li>
      )}
    </ol>
  );
}
export function HeroPanel({ children, symbol = '₽' }: { children: ReactNode; symbol?: string }) {
  const reduced = useReducedMotion();
  return (
    <motion.section
      initial={reduced ? false : { opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', bounce: 0, duration: 0.4 }}
      className="hero"
    >
      <span aria-hidden className="hero-symbol">
        {symbol}
      </span>
      <div className="hero-content">{children}</div>
    </motion.section>
  );
}
export function KeyValue({
  label,
  value,
  source,
}: {
  label: string;
  value: ReactNode;
  source?: string;
}) {
  return (
    <div className="key-value">
      <span className="muted small">{label}</span>
      <strong>{value}</strong>
      {source && <SourceBadge>{source}</SourceBadge>}
    </div>
  );
}
export function CompanyCard({ company }: { company: Company }) {
  if (company.server)
    return (
      <Card>
        <h3>Ваш бизнес</h3>
        <h2>{company.name}</h2>
        <dl className="details">
          <dt>ИНН</dt>
          <dd>{company.inn || 'Нет данных'}</dd>
          <dt>ОКВЭД</dt>
          <dd>{company.okved || 'Нет данных'}</dd>
          <dt>Регистрация</dt>
          <dd>{company.registered || 'Нет данных'}</dd>
        </dl>
      </Card>
    );

  return (
    <Card>
      <h3>Ваш бизнес</h3>
      <h2 className="company-name">{company.name}</h2>
      <div className="chips">
        <span className="status status-OFFERED">Действующий</span>
        <SourceBadge>Микропредприятие</SourceBadge>
      </div>
      <dl className="details">
        <dt>ИНН</dt>
        <dd>{company.inn}</dd>
        <dt>ОКВЭД</dt>
        <dd>{company.okved}</dd>
        <dt>Источник</dt>
        <dd>{company.entity === 'IP' ? 'ЕГРИП' : 'ЕГРЮЛ'} · демо-снимок</dd>
      </dl>
    </Card>
  );
}
export function MonthlyBars({ values }: { values: number[] }) {
  const months = [
    'окт',
    'ноя',
    'дек',
    'янв',
    'фев',
    'мар',
    'апр',
    'май',
    'июн',
    'июл',
    'авг',
    'сен',
  ];
  return (
    <figure>
      <div className="monthly-bars" aria-hidden>
        {values.map((v, i) => (
          <div className="month" key={i}>
            <div
              className={`bar ${i === values.indexOf(Math.min(...values)) ? 'negative' : ''}`}
              style={{ height: `${(v / Math.max(...values, 0.01)) * 120}px` }}
            />
            <span>{months[i]}</span>
          </div>
        ))}
      </div>
      <figcaption className="small muted">
        Поступления за октябрь 2025 — сентябрь 2026, млн ₽.{' '}
        <details>
          <summary>Числа по месяцам</summary>
          <p>{values.map((v, i) => `${months[i]}: ${decimal(v)}`).join(' · ')}</p>
        </details>
      </figcaption>
    </figure>
  );
}
// Factor categories and synthetic contributions are intentionally not displayed.
export function FactorBars(_props: { bank?: boolean; showValues?: boolean }) {
  return null;
}
export function CoverageMeter({ value }: { value: number }) {
  return (
    <div className="coverage">
      <div className="spread">
        <span>Покрытие платежей</span>
        <strong className={value < MIN_COVERAGE ? 'red-text' : 'positive-text'}>
          {decimal(value)}×
        </strong>
      </div>
      <div
        className="meter"
        role="meter"
        aria-label="Покрытие платежей"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={Math.max(3, value)}
      >
        <span style={{ width: `${Math.min(value / 3, 1) * 100}%` }} />
        <i style={{ left: `${(MIN_COVERAGE / 3) * 100}%` }} />
      </div>
      <p className="small muted">Минимум по демо-политике — 1,3×</p>
    </div>
  );
}
export function AuditLog({ app }: { app: Application }) {
  return (
    <ol className="audit">
      {app.history.map((event) => (
        <li key={event.id}>
          <time>{datetime(event.at)}</time>
          <div>
            <strong>{event.text}</strong>
            <p className="small muted">
              {event.actor} · ревизия {event.revision}
            </p>
            <details>
              <summary className="small muted">Основание</summary>
              <p className="small">
                {event.model} · {event.policy}
                <br />
                {event.snapshot}
              </p>
            </details>
          </div>
        </li>
      ))}
    </ol>
  );
}
export function AssistantTeaser({ onOpen }: { onOpen: () => void }) {
  return (
    <Card className="assistant-teaser">
      <h3>
        <span className="assistant-icon">
          <MessageCircle aria-hidden size={20} />
        </span>
        Помощник
      </h3>
      <div className="bubble user">Почему банк смотрит кредитную историю, если я ИП?</div>
      <div className="bubble assistant">
        У ИП личные и деловые долги связаны. Банк проверит историю только после вашего согласия.
      </div>
      <Action tone="soft" onClick={onOpen}>
        Спросить о заявке <ArrowRight aria-hidden size={18} />
      </Action>
    </Card>
  );
}
export function ProvenanceTable({ app, company }: { app: Application; company: Company }) {
  const registrationCode = `${app.product}_${company.entity === 'IP' ? '10' : '09'}`;
  const corrected = !!app.sources[registrationCode];
  const dataStatus = app.fieldStatuses?.[registrationCode];
  const statusLabels = {
    CONFIRMED: 'Подтверждено',
    UNVERIFIED: 'Не проверено',
    CONFLICT: 'Конфликт',
    STALE: 'Устарело',
  };
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Поле</th>
            <th>Значение</th>
            <th>Источник</th>
            <th>Статус</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>ИНН / регистрация</td>
            <td>
              {app.fields[`${app.product}_03`] || company.inn}
              <br />
              {app.fields[registrationCode] || company.registration}
            </td>
            <td>
              <SourceBadge>
                {corrected
                  ? app.sources[registrationCode]
                  : company.entity === 'IP'
                    ? 'ЕГРИП'
                    : 'ЕГРЮЛ'}
              </SourceBadge>
            </td>
            <td>
              <span
                className={`status ${corrected || (dataStatus && dataStatus !== 'CONFIRMED') ? 'status-NEEDS_INFO' : 'status-OFFERED'}`}
              >
                {dataStatus
                  ? statusLabels[dataStatus]
                  : corrected
                    ? 'Исправлено клиентом'
                    : 'Подтверждено'}
              </span>
            </td>
          </tr>
          <tr>
            <td>Свободный поток</td>
            <td>{money(app.flow)} / мес.</td>
            <td>
              <SourceBadge>Выписка</SourceBadge>
            </td>
            <td>Демо-снимок</td>
          </tr>
          {company.id === 'zerno' && (
            <tr className={app.checks?.revenue ? '' : 'conflict'}>
              <td>Выручка 2025</td>
              <td>38,4 млн ₽ / 33,9 млн ₽</td>
              <td>
                <SourceBadge>ГИР БО, выписка</SourceBadge>
              </td>
              <td>
                <span
                  className={`status ${app.checks?.revenue ? 'status-OFFERED' : 'status-NEEDS_INFO'}`}
                >
                  {app.checks?.revenue ? 'Подтверждено' : 'Конфликт'}
                </span>
              </td>
            </tr>
          )}
          <tr>
            <td>Действующие платежи</td>
            <td>{money(app.existing)}</td>
            <td>
              <SourceBadge>Клиент, БКИ</SourceBadge>
            </td>
            <td>
              {app.leasing === null ? (
                'Нужно уточнение'
              ) : (
                <>
                  <Check aria-hidden size={16} /> Уточнено
                </>
              )}
            </td>
          </tr>
          <tr>
            <td>Подписант</td>
            <td>{app.fields[`${app.product}_29`]}</td>
            <td>
              <SourceBadge>Клиент</SourceBadge>
            </td>
            <td>{app.checks?.authority ? 'Полномочия подтверждены' : 'Не проверено'}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
export function ApplicationFields({
  app,
  company,
  showCodes = true,
}: {
  app: Application;
  company: Company;
  showCodes?: boolean;
}) {
  return (
    <div className="table-scroll">
      <table>
        <thead>
          <tr>
            <th>Поле</th>
            <th>Значение</th>
            <th>Источник</th>
          </tr>
        </thead>
        <tbody>
          {applicableFields(app.product, company.entity).map((field) => (
            <tr
              key={field.code}
              className={app.originalFields?.[field.code] ? 'conflict' : undefined}
            >
              <td>
                {field.label}
                {showCodes && <span className="small muted block">{field.code}</span>}
              </td>
              <td>
                {app.fields[field.code] || 'Не заполнено'}
                {app.originalFields?.[field.code] && (
                  <span className="small muted block">
                    Исходно: {app.originalFields[field.code]}
                  </span>
                )}
              </td>
              <td>
                <SourceBadge>{app.sources[field.code] || field.source}</SourceBadge>
                {showCodes && app.fieldStatuses?.[field.code] === 'STALE' && (
                  <span className="block small attention-text">
                    Устарело — нужен актуальный источник
                  </span>
                )}
                {showCodes && app.originalFields?.[field.code] && (
                  <span className="block small attention-text">
                    Конфликт: исправлено со слов клиента
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
