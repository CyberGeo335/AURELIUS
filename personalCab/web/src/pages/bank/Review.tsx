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
import { coverage, decimal, money, payment } from '../../domain/finance';
import { products, type Application, type BankAction } from '../../domain/types';
import { demoRisk } from '../../domain/risk';
function DecisionPanel({ app }: { app: Application }) {
  const api = useApi();
  const action = useAction();
  const [choice, setChoice] = useState<BankAction>('A');
  const [reason, setReason] = useState('');
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
      {app.status === 'MANUAL_REVIEW' ? (
        <>
          <fieldset>
            <legend className="sr-only">Решение по заявке</legend>
            {options.map(([key, title, desc]) => (
              <label className={`radio-option ${choice === key ? 'selected' : ''}`} key={key}>
                <input
                  type="radio"
                  name="bankDecision"
                  checked={choice === key}
                  onChange={() => setChoice(key)}
                />
                <span>
                  <strong>{title}</strong>
                  <span className="small muted block">{desc}</span>
                </span>
              </label>
            ))}
          </fieldset>
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
          <ErrorState message={action.error} />
          <Action
            className="full-width"
            disabled={action.busy || reason.trim().length < 15}
            onClick={() => action.run(() => api.bankDecision(app.id, app.revision, choice, reason))}
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
export function Review() {
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
      {app.status === 'DECLINED' && (
        <Card>
          <h2>Решение: отказ</h2>
          <p className="red-text">{app.reasonCode}</p>
          <p>{app.reason}</p>
        </Card>
      )}
      <div className="review-layout">
        <div className="stack">
          {app.status === 'MANUAL_REVIEW' && (
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
                    <h3>Выручка за 2025 в источниках расходится на 12%</h3>
                    <p className="muted small">ГИР БО 38,4 млн ₽, выписка 33,9 млн ₽.</p>
                  </div>
                )}
              </div>
            </Card>
          )}
          <div className="two-columns">
            <Card>
              <div className="spread">
                <h3>Оценка модели</h3>
                <span className="small muted">score-model v0.3</span>
              </div>
              <div className="metrics">
                <KeyValue label="Уровень риска" value={demoRisk(app).label} />
                <KeyValue label="PD, 12 мес." value={demoRisk(app).pd} />
              </div>
              {company.id === 'zerno' ? (
                <FactorBars bank />
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
