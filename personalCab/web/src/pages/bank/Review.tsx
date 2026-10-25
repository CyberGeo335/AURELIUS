import { BusinessReview } from '../../business/BusinessPages';
import { displayStatus } from '../../domain/status';
import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { useApi, useCredit, useAction } from '../../app/context';
import {
  Action,
  Card,
  StageTrack,
  StatusBadge,
  AuditLog,
  ProvenanceTable,
  ApplicationFields,
  ErrorState,
  EmptyState,
  FactorBars,
  CoverageMeter,
  KeyValue,
} from '../../components/v2/primitives';
import { Textarea } from '../../components/ui/textarea';
import { Input } from '../../components/ui/input';
import { coverage, decimal, money, payment } from '../../domain/finance';
import { products, type Application, type BankAction } from '../../domain/types';
import { requiredChecks } from '../../domain/review';
import { demoRisk } from '../../domain/risk';
function DecisionPanel({ app }: { app: Application }) {
  const api = useApi();
  const action = useAction();
  const [choice, setChoice] = useState<BankAction>('A');
  const [reason, setReason] = useState('');
  const [requestField, setRequestField] = useState('statement');
  const [due, setDue] = useState(new Date(Date.now() + 3 * 86400000).toISOString().slice(0, 10));
  const amountA = Math.round((app.amount * 2200000) / 3000000);
  const options: [BankAction, string, string][] = [
    [
      'A',
      'Предложить вариант А',
      `${money(amountA)} · ${app.term} мес. · ${money(payment(amountA, app.term))}/мес.`,
    ],
    [
      'B',
      'Предложить вариант Б',
      `${money(app.amount)} · 24 мес. · ${money(payment(app.amount, 24))}/мес.`,
    ],
    ['BOTH', 'Предложить оба варианта', 'Клиент выберет сам'],
    ['INFO', 'Запросить данные', 'Укажите, чего не хватает для решения'],
    ['DECLINE', 'Отказать', 'Код причины: MANUAL_POLICY_DECLINE'],
  ];
  const checksReady = requiredChecks(app).ready;
  const allowed = (key: BankAction) =>
    key === 'INFO' ||
    key === 'DECLINE' ||
    (checksReady &&
      (key === 'A'
        ? coverage(app.flow, app.existing, amountA, app.term) >= 1.3
        : key === 'B'
          ? coverage(app.flow, app.existing, app.amount, 24) >= 1.3
          : coverage(app.flow, app.existing, amountA, app.term) >= 1.3 &&
            coverage(app.flow, app.existing, app.amount, 24) >= 1.3));
  const preview =
    choice === 'INFO'
      ? 'Банк просит уточнить данные: ' + reason
      : choice === 'DECLINE'
        ? 'Сейчас не можем одобрить. ' + reason
        : choice === 'BOTH'
          ? 'Банк предлагает два варианта. Выберите подходящие сумму и срок.'
          : `Банк готов выдать ${money(choice === 'A' ? amountA : app.amount)} на ${choice === 'A' ? app.term : 24} мес.`;
  return (
    <aside className="dark decision-panel">
      <h2>Ваше решение</h2>
      {displayStatus(app) === 'MANUAL_REVIEW' ? (
        <>
          <fieldset>
            <legend className="sr-only">Решение по заявке</legend>
            {options.map(([key, title, desc]) => (
              <label className={`radio-option ${choice === key ? 'selected' : ''}`} key={key}>
                <input
                  type="radio"
                  name="bankDecision"
                  checked={choice === key}
                  disabled={!allowed(key)}
                  onChange={() => setChoice(key)}
                />
                <span>
                  <strong>{title}</strong>
                  <span className="small muted block">{desc}</span>
                  {!allowed(key) && (
                    <span className="small attention-text block">
                      {checksReady
                        ? 'Покрытие ниже допустимого порога'
                        : 'Сначала завершите проверки досье'}
                    </span>
                  )}
                </span>
              </label>
            ))}
          </fieldset>
          {choice === 'INFO' && (
            <div className="form-fields">
              <label className="form-field">
                Что запросить
                <select value={requestField} onChange={(e) => setRequestField(e.target.value)}>
                  <option value="statement">Выписка по счёту</option>
                  <option value="authority">Доверенность подписанта</option>
                  <option value="revenue">Пояснение по выручке</option>
                  <option value="clarification">Уточнение поля анкеты</option>
                </select>
              </label>
              <label className="form-field">
                Срок ответа
                <Input
                  type="date"
                  value={due}
                  min={new Date(Date.now() + 86400000).toISOString().slice(0, 10)}
                  onChange={(e) => setDue(e.target.value)}
                />
              </label>
            </div>
          )}
          <label className="form-field">
            Обоснование — обязательно
            <Textarea
              rows={4}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              aria-invalid={reason.length > 0 && reason.trim().length < 15}
              placeholder={
                choice === 'INFO'
                  ? 'Какие данные нужны и за какой период?'
                  : 'Почему принято это решение? Не менее 15 символов.'
              }
            />
          </label>
          <p className="small muted">Текст получит клиент. Не включайте внутренние сведения.</p>
          <ErrorState message={action.error} onRetry={action.retry} />
          <Action
            className="full-width"
            disabled={
              action.busy ||
              reason.trim().length < 15 ||
              !allowed(choice) ||
              (choice === 'INFO' && (!due || new Date(due).getTime() <= Date.now()))
            }
            onClick={() =>
              action.run(() =>
                api.bankDecision(
                  app.id,
                  app.revision,
                  choice,
                  reason,
                  choice === 'INFO'
                    ? { field: requestField, dueAt: new Date(due + 'T20:59:00Z').getTime() }
                    : undefined,
                ),
              )
            }
          >
            {action.busy ? 'Сохраняем…' : 'Сохранить решение'}
          </Action>
          <div className="inset">
            <strong>Клиент увидит:</strong>
            <p>{preview}</p>
            {['A', 'B', 'BOTH'].includes(choice) && <p>{reason}</p>}
          </div>
        </>
      ) : (
        <>
          <StatusBadge app={app} />
          <p>Состояние заявки обновлено. Решение уже доступно в кабинете клиента.</p>
        </>
      )}
      <hr />
      <p className="muted">Журнал</p>
      <AuditLog app={app} />
    </aside>
  );
}
function DataChecks({ app }: { app: Application }) {
  const api = useApi();
  const action = useAction();
  const [comment, setComment] = useState('');
  const [source, setSource] = useState(
    app.companyId === 'zerno' ? 'ГИР БО: 38,4 млн ₽' : 'Уточнённые сведения клиента',
  );
  return (
    <Card>
      <h3>Обязательные проверки досье</h3>
      <p className="muted small">
        Чтобы предложить условия, подтвердите полномочия и разрешите расхождения. Комментарий
        сохранится в журнале.
      </p>
      <label className="form-field">
        Комментарий к проверке
        <Textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Документ, источник и основание проверки"
        />
      </label>
      <ErrorState message={action.error} onRetry={action.retry} />
      {requiredChecks(app).authority && (
        <div className="data-check-row">
          <div>
            <strong>Полномочия подписанта</strong>
            <p className="small muted">
              {app.checks?.authority ? 'Подтверждены' : 'Доверенность № 14 требует проверки'}
            </p>
          </div>
          <Action
            tone="soft"
            disabled={action.busy || comment.trim().length < 10 || app.checks?.authority}
            onClick={() => action.run(() => api.resolveData(app.id, 'authority', comment))}
          >
            Подтвердить полномочия
          </Action>
        </div>
      )}
      {requiredChecks(app).revenue && (
        <div className="data-check-row">
          <label className="form-field">
            Основное значение выручки
            <select value={source} onChange={(e) => setSource(e.target.value)}>
              {app.companyId === 'zerno' ? (
                <>
                  <option>ГИР БО: 38,4 млн ₽</option>
                  <option>Выписка: 33,9 млн ₽</option>
                </>
              ) : (
                <>
                  <option>Уточнённые сведения клиента</option>
                  <option>Подтверждённый первичный источник</option>
                </>
              )}
            </select>
          </label>
          <Action
            tone="soft"
            disabled={action.busy || comment.trim().length < 10 || app.checks?.revenue}
            onClick={() =>
              action.run(() => api.resolveData(app.id, 'revenue', `${source}. ${comment}`))
            }
          >
            {app.checks?.revenue ? 'Конфликт разрешён' : 'Подтвердить источник'}
          </Action>
        </div>
      )}
    </Card>
  );
}
function MockReview() {
  const { id } = useParams();
  const state = useCredit();
  const app = state.applications.find((a) => a.id === id);
  if (!app)
    return (
      <EmptyState title="Заявка не найдена">
        <Link to="/bank">Вернуться к очереди</Link>
      </EmptyState>
    );
  const company = state.companies.find((c) => c.id === app.companyId)!;
  const ratio = coverage(app.flow, app.existing, app.amount, app.term);
  const amountA = Math.round((app.amount * 2200000) / 3000000);
  return (
    <>
      <div className="page-title">
        <div>
          <div className="chips">
            <StatusBadge app={app} />
            <span className="source">ревизия {app.revision}</span>
            <span className="source">{app.id}</span>
          </div>
          <h1>{company.name}</h1>
          <p className="muted">
            {products[app.product]}: {money(app.amount)} на {app.term} месяцев,{' '}
            {app.purpose.toLowerCase()}
          </p>
        </div>
        <div className="actions">
          <Action tone="white" asChild>
            <a href="#dossier">Анкета клиента</a>
          </Action>
          <Action tone="white" asChild>
            <a href="#documents">Документы</a>
          </Action>
        </div>
      </div>
      <StageTrack app={app} bank />
      {displayStatus(app) === 'DECLINED' && (
        <Card>
          <h2>Решение: отказ</h2>
          <p className="red-text">{app.reasonCode}</p>
          <p>{app.reason}</p>
        </Card>
      )}
      <div className="review-layout">
        <div className="stack">
          {displayStatus(app) === 'MANUAL_REVIEW' && (
            <Card className="reason-card">
              <h2>Почему автоматика остановилась</h2>
              <div className="two-columns">
                <div className="inset">
                  <p className="red-text small">{app.reasonCode.split(',')[0]}</p>
                  <h3>
                    {ratio < 1.3
                      ? `Покрытие платежей ${decimal(ratio)}× при минимуме 1,3×`
                      : app.reason}
                  </h3>
                  <p className="muted small">
                    С новым платежом {money(payment(app.amount, app.term))} нужно проверить
                    достаточность данных и запас прочности.
                  </p>
                </div>
                {company.id === 'zerno' && (
                  <div className="inset">
                    <p className="attention-text small">DATA_CONFLICT</p>
                    <h3>
                      {app.checks?.revenue
                        ? 'Конфликт выручки разобран'
                        : 'Выручка за 2025 в источниках расходится на 12%'}
                    </h3>
                    <p className="muted small">ГИР БО 38,4 млн ₽, выписка 33,9 млн ₽.</p>
                  </div>
                )}
              </div>
            </Card>
          )}
          {displayStatus(app) === 'MANUAL_REVIEW' &&
            (requiredChecks(app).authority || requiredChecks(app).revenue) && (
              <DataChecks app={app} />
            )}
          <div className="two-columns">
            <Card>
              <div className="spread">
                <h3>Оценка модели</h3>
                <span className="small muted">score-model v0.3</span>
              </div>
              <p className="small muted">
                Снимок от{' '}
                {new Date(app.sourceDate ?? app.created).toLocaleString('ru-RU', {
                  timeZone: 'Europe/Moscow',
                })}{' '}
                · ревизия {app.revision}
              </p>
              <div className="metrics">
                <KeyValue label="PD, 12 мес." value={demoRisk(app).pd} />
              </div>
              {['zerno', 'karpov'].includes(company.id) ? (
                <FactorBars bank={company.id === 'zerno'} showValues={company.id === 'zerno'} />
              ) : (
                <p className="muted small">Вклад факторов для этой заявки в демо не рассчитан.</p>
              )}
              <p className="small muted">
                Синтетическая оценка из макета. Реальная модель не подключена.
              </p>
            </Card>
            <Card>
              <h3>Платёжеспособность</h3>
              <dl className="details">
                <dt>Свободный поток в месяц</dt>
                <dd>{money(app.flow)}</dd>
                <dt>Действующие платежи</dt>
                <dd>{money(app.existing)}</dd>
                <dt>Новый платёж</dt>
                <dd>{money(payment(app.amount, app.term))}</dd>
              </dl>
              <CoverageMeter value={ratio} />
              <p className="small muted">Подбираем условия с покрытием не ниже 1,3×</p>
              <table className="compact-table">
                <tbody>
                  {[
                    ['Как просил', app.amount, app.term],
                    ['Вариант А', amountA, app.term],
                    ['Вариант Б', app.amount, 24],
                  ].map(([label, amount, term]) => (
                    <tr key={label}>
                      <th>{label}</th>
                      <td>
                        {money(Number(amount))}
                        <br />
                        {term} мес.
                      </td>
                      <td
                        className={
                          coverage(app.flow, app.existing, Number(amount), Number(term)) < 1.3
                            ? 'red-text'
                            : 'positive-text'
                        }
                      >
                        {decimal(coverage(app.flow, app.existing, Number(amount), Number(term)))}×
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Card>
          </div>
          <Card id="dossier">
            <h3>Досье</h3>
            <ProvenanceTable app={app} company={company} />
            <details>
              <summary>Все поля анкеты</summary>
              <ApplicationFields app={app} company={company} />
            </details>
          </Card>
          <Card id="documents">
            <h3>Документы и ответы</h3>
            {app.files.length ? (
              <ul>
                {app.files.map((file, i) => (
                  <li key={i}>{file} · имя файла, демо-загрузка</li>
                ))}
              </ul>
            ) : (
              <p className="muted">
                Пользовательские файлы не добавлены. Исходный снимок данных — демонстрационный.
              </p>
            )}
            {app.requests.map((r) => (
              <p key={r.id}>
                <strong>{r.text}</strong>
                <br />
                {r.state === 'OPEN' ? 'Ожидаем ответ' : r.answer || r.file}
              </p>
            ))}
          </Card>
        </div>
        <DecisionPanel key={`${app.id}-${app.revision}`} app={app} />
      </div>
    </>
  );
}

export function Review() {
  return import.meta.env.VITE_API_MODE === 'http' ? <BusinessReview /> : <MockReview />;
}
