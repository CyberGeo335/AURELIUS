import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { Check, FileText, ArrowRight } from 'lucide-react';
import { useApi, useCredit, useSession, useAction } from '../../app/context';
import {
  Action,
  Card,
  StageTrack,
  HeroPanel,
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
import { Input } from '../../components/ui/input';
import { AnimatedMoney } from '../../components/v2/AnimatedMoney';
import { Textarea } from '../../components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '../../components/ui/dialog';
import { coverage, date, money, payment, schedule } from '../../domain/finance';
import { products, type Application, type DataRequest } from '../../domain/types';
function RequestAnswer({ app, request }: { app: Application; request: DataRequest }) {
  const api = useApi();
  const action = useAction();
  const [answer, setAnswer] = useState('');
  const [file, setFile] = useState('');
  return (
    <Card className="dark">
      <p className="attention-text">Нужен ваш ответ</p>
      <h2>{request.text}</h2>
      <p className="muted">После ответа проверка продолжится в этой же заявке.</p>
      <ErrorState message={action.error} />
      {request.field === 'leasing' ? (
        <div className="actions">
          <Action
            disabled={action.busy}
            onClick={() =>
              action.run(() => api.answerRequest(app.id, request.id, 'Да, это лизинг'))
            }
          >
            Да, это лизинг
          </Action>
          <Action
            tone="outline"
            disabled={action.busy}
            onClick={() =>
              action.run(() => api.answerRequest(app.id, request.id, 'Нет, это другой платёж'))
            }
          >
            Нет, другое
          </Action>
        </div>
      ) : (
        <>
          <label className="form-field">
            Ответ банку
            <Textarea
              value={answer}
              onChange={(e) => setAnswer(e.target.value)}
              placeholder="Уточнение к заявке"
            />
          </label>
          <label className="file-button">
            Добавить PDF / CSV
            <input
              type="file"
              accept=".pdf,.csv"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) {
                  if (!/\.(pdf|csv)$/i.test(f.name) || f.size > 10 * 1024 * 1024) {
                    action.setError('Нужен PDF или CSV до 10 МБ.');
                    return;
                  }
                  setFile(f.name);
                }
              }}
            />
          </label>
          <p className="small muted">
            {file || 'Файл остаётся в браузере; сохраняется только имя, анализ имитируется.'}
          </p>
          <Action
            disabled={action.busy || (!answer.trim() && !file)}
            onClick={() =>
              action.run(() => api.answerRequest(app.id, request.id, answer, file || undefined))
            }
          >
            Отправить данные
          </Action>
        </>
      )}
    </Card>
  );
}
function Decision({ app }: { app: Application }) {
  const api = useApi();
  const action = useAction();
  const [selected, setSelected] = useState(app.offers[0]?.id ?? '');
  const [newAmount, setNewAmount] = useState(String(app.amount));
  const [changeOpen, setChangeOpen] = useState(false);
  const offer = app.offers.find((o) => o.id === selected) ?? app.offers[0];
  if (!offer) return <EmptyState title="Предложение готовится" />;
  const monthly = payment(offer.amount, offer.term);
  const ratio = coverage(app.flow, app.existing, offer.amount, offer.term);
  const expired = offer.expires <= Date.now();
  return (
    <>
      <ErrorState message={action.error} />
      <div className="decision-grid">
        <HeroPanel>
          <div className="spread">
            <span className="status">
              <Check aria-hidden size={16} />{' '}
              {offer.kind === 'COUNTEROFFER' ? 'Новые условия' : 'Одобрено'}
            </span>
            <span className="hero-eyebrow">Демо-условия, до {date(offer.expires)}</span>
          </div>
          <h2 className="decision-intro">Банк готов выдать</h2>
          <div className="decision-amount">
            <AnimatedMoney value={offer.amount} />
          </div>
          <p>
            {offer.kind === 'COUNTEROFFER'
              ? 'На условиях, которые подходят вашему бизнесу.'
              : 'Всю запрошенную сумму, на ' + app.purpose.toLowerCase()}
          </p>
          {app.offers.length > 1 && (
            <fieldset className="offer-options">
              <legend>Выберите предложение</legend>
              {app.offers.map((o) => (
                <label className="radio-option" key={o.id}>
                  <input
                    type="radio"
                    name="offer"
                    checked={offer.id === o.id}
                    onChange={() => setSelected(o.id)}
                  />
                  <span>
                    {o.label}: {money(o.amount)} · {o.term} мес.
                  </span>
                </label>
              ))}
            </fieldset>
          )}
          <fieldset className="term-selector">
            <legend>Срок · изменение запускает перепроверку</legend>
            {[12, 18, 24].map((term) => (
              <button
                disabled={action.busy}
                type="button"
                aria-pressed={offer.term === term}
                key={term}
                onClick={() => {
                  if (term !== offer.term)
                    void action.run(() => api.revise(app.id, offer.amount, term));
                }}
              >
                {term} мес.
              </button>
            ))}
          </fieldset>
          <div className="decision-numbers">
            <KeyValue
              label={
                app.product === 'R01' ? 'Платёж в месяц' : 'Пример платежа при полном использовании'
              }
              value={money(monthly)}
            />
            <KeyValue label="Демо-ставка" value="24,9%" />
            <KeyValue label="Переплата" value={money(monthly * offer.term - offer.amount)} />
          </div>
          {app.product !== 'R01' && (
            <p className="product-disclaimer">
              {app.product === 'R02'
                ? `Возобновляемый лимит. Транш: ${app.fields.R02_32} мес., выборка: ${app.fields.R02_33} мес.`
                : `Счёт: ${app.fields.R03_32}. Погашение из поступлений.`}{' '}
              Расчёт выше иллюстративный: полное использование лимита с аннуитетом. Фактический
              график зависит от использования.
            </p>
          )}
          <div className="actions">
            <Action
              tone="ink"
              disabled={action.busy || expired}
              onClick={() => action.run(() => api.accept(app.id, offer.id))}
            >
              Принять предложение
            </Action>
            <Dialog open={changeOpen} onOpenChange={setChangeOpen}>
              <DialogTrigger asChild>
                <Action tone="outline">Изменить сумму</Action>
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>Изменить сумму</DialogTitle>
                  <DialogDescription>
                    Старое предложение будет отозвано. Банк проверит новую ревизию заявки.
                  </DialogDescription>
                </DialogHeader>
                <label className="form-field">
                  Сумма, ₽
                  <Input
                    type="number"
                    min={100000}
                    max={5000000}
                    value={newAmount}
                    onChange={(e) => setNewAmount(e.target.value)}
                  />
                </label>
                <ErrorState message={action.error} />
                <Action
                  disabled={action.busy}
                  onClick={() =>
                    action.run(async () => {
                      await api.revise(app.id, Number(newAmount), offer.term);
                      setChangeOpen(false);
                    })
                  }
                >
                  Отправить на перепроверку
                </Action>
              </DialogContent>
            </Dialog>
          </div>
          {expired && (
            <div className="inset dark">
              <p>Срок предложения истёк.</p>
              <Action
                tone="white"
                onClick={() => action.run(() => api.revise(app.id, offer.amount, offer.term))}
              >
                Получить новое предложение
              </Action>
            </div>
          )}
        </HeroPanel>
        <div className="stack">
          <Card>
            <h2>{offer.kind === 'COUNTEROFFER' ? 'Почему другие условия' : 'Почему одобрили'}</h2>
            {app.reason && <p>{app.reason}</p>}
            <p className="muted small">Демо-факторы. Чем длиннее полоса, тем сильнее влияние.</p>
            <FactorBars bank={app.companyId !== 'karpov'} />
            <CoverageMeter value={ratio} />
          </Card>
          <Card className="dark">
            <p className="muted">Первые платежи</p>
            <div className="metrics">
              {schedule(offer.amount, offer.term, app.updated)
                .slice(0, 3)
                .map((row) => (
                  <KeyValue key={row.date} label={date(row.date)} value={money(row.payment)} />
                ))}
            </div>
            <Dialog>
              <DialogTrigger asChild>
                <button className="text-button">Весь график</button>
              </DialogTrigger>
              <DialogContent className="wide-dialog">
                <DialogHeader>
                  <DialogTitle>Демонстрационный график</DialogTitle>
                  <DialogDescription>
                    Аннуитет, 24,9% годовых. Суммы округлены для отображения.
                  </DialogDescription>
                </DialogHeader>
                <div className="table-scroll">
                  <table>
                    <thead>
                      <tr>
                        <th>Дата</th>
                        <th>Платёж</th>
                        <th>Проценты</th>
                        <th>Остаток</th>
                      </tr>
                    </thead>
                    <tbody>
                      {schedule(offer.amount, offer.term, app.updated).map((row) => (
                        <tr key={row.date}>
                          <td>{date(row.date)}</td>
                          <td>{money(row.payment)}</td>
                          <td>{money(row.interest)}</td>
                          <td>{money(row.balance)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </DialogContent>
            </Dialog>
          </Card>
        </div>
      </div>
      <h2>Дальше три шага</h2>
      <div className="next-steps">
        <div>Примите предложение</div>
        <div>Подпишите договор в кабинете</div>
        <div>Деньги придут на счёт</div>
      </div>
    </>
  );
}
function Signing({ app }: { app: Application }) {
  const api = useApi();
  const action = useAction();
  const [confirm, setConfirm] = useState(false);
  return (
    <Card className="signing">
      <span className="status status-OFFERED">DEMO · имитация</span>
      <h1>
        {app.status === 'FUNDED_DEMO'
          ? 'Деньги на счёте'
          : app.status === 'SIGNED_DEMO'
            ? 'Договор подписан'
            : 'Подтвердите условия'}
      </h1>
      <p className="muted">
        Подпись и выдача имитируются на демо-стенде. Реальные банковские операции не выполняются.
      </p>
      {app.acceptedOffer && (
        <div className="metrics">
          <KeyValue label="Сумма" value={money(app.acceptedOffer.amount)} />
          <KeyValue label="Срок" value={`${app.acceptedOffer.term} мес.`} />
          <KeyValue
            label="Платёж"
            value={money(payment(app.acceptedOffer.amount, app.acceptedOffer.term))}
          />
        </div>
      )}
      <ErrorState message={action.error} />
      {app.status === 'ACCEPTED' && (
        <>
          <label className="check-row">
            <input
              type="checkbox"
              checked={confirm}
              onChange={(e) => setConfirm(e.target.checked)}
            />
            Я проверил условия и подтверждаю демонстрационную подпись.
          </label>
          <Action
            disabled={!confirm || action.busy}
            onClick={() => action.run(() => api.sign(app.id))}
          >
            Подписать · DEMO
          </Action>
        </>
      )}
      {app.status === 'SIGNED_DEMO' && (
        <Action disabled={action.busy} onClick={() => action.run(() => api.fund(app.id))}>
          Имитировать выдачу <ArrowRight aria-hidden size={18} />
        </Action>
      )}
      {app.status === 'FUNDED_DEMO' && (
        <p className="positive-text">
          <Check aria-hidden /> Демо-сценарий завершён
        </p>
      )}
    </Card>
  );
}
export function ApplicationDetail() {
  const { id } = useParams();
  const state = useCredit();
  const api = useApi();
  const { session } = useSession();
  const action = useAction();
  const app = state.applications.find((a) => a.id === id && a.companyId === session!.profile);
  if (!app)
    return (
      <EmptyState title="Заявка не найдена">
        <Link to="/client/applications">Все заявки</Link>
      </EmptyState>
    );
  const company = state.companies.find((c) => c.id === app.companyId)!;
  return (
    <>
      <div className="spread">
        <Link className="back-link" to="/client/applications">
          ← Все заявки
        </Link>
        <span className="muted small">
          {app.id} · ревизия {app.revision}
        </span>
      </div>
      {app.status === 'OFFERED' ? (
        <Decision key={app.revision} app={app} />
      ) : ['ACCEPTED', 'SIGNED_DEMO', 'FUNDED_DEMO'].includes(app.status) ? (
        <Signing app={app} />
      ) : (
        <>
          <HeroPanel>
            <StatusBadge app={app} />
            <h1>
              {app.status === 'DECLINED'
                ? 'Сейчас не можем одобрить'
                : app.status === 'MANUAL_REVIEW'
                  ? 'Заявка у специалиста'
                  : app.status === 'NEEDS_INFO'
                    ? 'Нужно ваше уточнение'
                    : app.status === 'CANCELLED'
                      ? 'Заявка отменена'
                      : 'Проверяем вашу заявку'}
            </h1>
            <p>
              {money(app.amount)} · {app.term} мес. · {products[app.product]}
            </p>
            <p>
              {app.status === 'DECLINED'
                ? app.reason
                : app.status === 'MANUAL_REVIEW'
                  ? 'Специалист изучит данные и подберёт допустимые условия. Это не отказ.'
                  : app.externalWait && app.status === 'CHECKING'
                    ? 'Источник временно недоступен. Ожидаем повторного ответа.'
                    : ''}
            </p>
            <StageTrack app={app} />
          </HeroPanel>
          {app.requests
            .filter((r) => r.state === 'OPEN')
            .map((r) => (
              <RequestAnswer key={r.id} app={app} request={r} />
            ))}
        </>
      )}
      <div className="two-columns">
        <Card>
          <h2>Досье заявки</h2>
          <ProvenanceTable app={app} company={company} />
          <p className="small muted">Источники — синтетические снимки для демонстрации.</p>
          <details>
            <summary>Анкета и источники данных</summary>
            <ApplicationFields app={app} company={company} />
          </details>
          <details>
            <summary>
              <FileText aria-hidden size={16} /> Документы и согласия
            </summary>
            <p>{app.files.length ? app.files.join(', ') : 'Пользовательские файлы не добавлены'}</p>
            <p>БКИ: {app.consentVersion ?? 'Согласие ещё не дано'}</p>
            {app.consentedAt && <p>Зафиксировано {date(app.consentedAt)}</p>}
          </details>
        </Card>
        <Card id="history">
          <h2>Что сделал банк</h2>
          <AuditLog app={app} />
          {app.revisions.length > 0 && (
            <details>
              <summary>Предыдущие ревизии ({app.revisions.length})</summary>
              {app.revisions.map((r) => (
                <p key={r.revision}>
                  Ревизия {r.revision} · {money(r.amount)} · {r.term} мес. — {r.reason}
                </p>
              ))}
            </details>
          )}
        </Card>
      </div>
      <ErrorState message={action.error} />
      {['DRAFT', 'SUBMITTED', 'CHECKING', 'NEEDS_INFO', 'MANUAL_REVIEW', 'OFFERED'].includes(
        app.status,
      ) && (
        <Dialog>
          <DialogTrigger asChild>
            <Action tone="ghost">Отменить заявку</Action>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Отменить заявку?</DialogTitle>
              <DialogDescription>
                Проверка остановится. История останется в кабинете, но возобновить эту заявку
                нельзя.
              </DialogDescription>
            </DialogHeader>
            <ErrorState message={action.error} />
            <Action disabled={action.busy} onClick={() => action.run(() => api.cancel(app.id))}>
              Подтвердить отмену
            </Action>
          </DialogContent>
        </Dialog>
      )}
    </>
  );
}
