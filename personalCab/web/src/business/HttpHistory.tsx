import { Link } from 'react-router';
import { Card, StatusBadge } from '../components/v2/primitives';
import { httpClientStatus } from '../domain/clientStatus';
import type { Application } from '../domain/types';

const bankLabels: Record<string, string> = {
  create: 'Заявка создана',
  save: 'Черновик сохранён',
  submit: 'Заявка отправлена',
  score: 'Запрошен скоринг',
  review: 'Сохранено решение сотрудника',
  verify: 'Зафиксирована проверка сотрудника',
  accept: 'Предложение принято',
  cancel: 'Заявка отменена',
  answer: 'Получен ответ на дозапрос',
  revise: 'Изменены запрошенные условия',
  upload: 'Документ загружен',
  claim: 'Заявка взята в работу',
  release: 'Ответственный освободил заявку',
  chat: 'Обработано сообщение ассистенту',
  confirm_facts: 'Подтверждены изменения анкеты',
  offer_stale: 'Предложение направлено на повторную проверку',
  accept_blocked: 'Принятие предложения заблокировано',
};
const clientLabels: Record<string, string> = {
  create: 'Заявка создана',
  submit: 'Вы отправили заявку',
  answer: 'Ваш ответ получен',
  upload: 'Документ загружен',
  review: 'Банк принял решение',
  accept: 'Вы приняли предложение',
  revise: 'Вы изменили условия',
  cancel: 'Заявка отменена',
  offer_stale: 'Данные изменились, требуется повторная проверка',
};
function rows(applications: Application[]) {
  return applications
    .flatMap((app) => (app.server?.history ?? []).map((event) => ({ app, event })))
    .sort(
      (a, b) =>
        Date.parse(b.event.created_at) - Date.parse(a.event.created_at) ||
        b.event.event_id - a.event.event_id,
    );
}
function EventTime({ value }: { value: string }) {
  const valid = Number.isFinite(Date.parse(value));
  return valid ? (
    <time dateTime={value}>
      {new Date(value).toLocaleString('ru-RU', { timeZone: 'Europe/Moscow' })}
    </time>
  ) : (
    <>—</>
  );
}
export function HttpBankHistory({
  applications,
  single = false,
}: {
  applications: Application[];
  single?: boolean;
}) {
  const events = rows(applications);
  return (
    <Card>
      <h2>{single ? 'Журнал заявки' : 'События заявок'}</h2>
      {events.length ? (
        <div className="http-history-table">
          <table>
            <thead>
              <tr>
                <th>Когда</th>
                {!single && <th>Заявка</th>}
                <th>Действие</th>
              </tr>
            </thead>
            <tbody>
              {events.map(({ app, event }) => (
                <tr key={`${app.id}-${event.event_id}`}>
                  <td>
                    <EventTime value={event.created_at} />
                  </td>
                  {!single && (
                    <td>
                      <Link to={`/bank/applications/${app.id}`}>{app.id}</Link>
                      <br />
                      <StatusBadge app={app} />
                    </td>
                  )}
                  <td>
                    {Object.hasOwn(bankLabels, event.action)
                      ? bankLabels[event.action]
                      : `Действие: ${event.action}`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="muted">Событий пока нет.</p>
      )}
    </Card>
  );
}
export function HttpClientJourney({ app }: { app: Application }) {
  const status = httpClientStatus(app);
  const events = rows([app])
    .filter(({ event }) => Object.hasOwn(clientLabels, event.action))
    .reverse();
  return (
    <Card id="history" className="client-journey">
      <h2>Ваша заявка</h2>
      <div className="client-next">
        <div>
          <strong>{status.happening}</strong>
          <p className="muted">{status.next}</p>
        </div>
      </div>
      {events.length ? (
        <ol className="client-timeline" aria-label="История заявки">
          {events.map(({ event }) => (
            <li key={event.event_id}>
              <span aria-hidden>•</span>
              <div>
                <strong>{clientLabels[event.action]}</strong>
                <EventTime value={event.created_at} />
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="muted">Событий пока нет.</p>
      )}
    </Card>
  );
}
