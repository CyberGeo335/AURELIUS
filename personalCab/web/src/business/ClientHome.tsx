import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ArrowUpRight, MessageCircle, ShieldCheck } from 'lucide-react';
import { useCredit, useSession } from '../app/context';
import {
  Action,
  Card,
  CompanyCard,
  EmptyState,
  HeroPanel,
  StageTrack,
  StatusBadge,
} from '../components/v2/primitives';
import { httpClientStatus } from '../domain/clientStatus';
import { displayStatus } from '../domain/status';
import { money } from '../domain/finance';
import { counted } from '../domain/text';
import { products, type Application } from '../domain/types';

const titles: Partial<Record<ReturnType<typeof displayStatus>, string>> = {
  DRAFT: 'Продолжим вашу заявку',
  SUBMITTED: 'Заявка отправлена',
  CHECKING: 'Проверяем заявку на',
  MANUAL_REVIEW: 'Специалист проверяет',
  NEEDS_INFO: 'Проверяем заявку на',
  OFFERED: 'Ваше предложение готово',
  ACCEPTED: 'Предложение принято',
  DECLINED: 'Решение по заявке',
  CANCELLED: 'Заявка отменена',
};
const amount = (app: Application) =>
  app.server?.requested_amount == null || app.server.requested_amount.trim() === ''
    ? 'Сумма не указана'
    : money(Number(app.server.requested_amount));
const term = (app: Application) =>
  app.server?.requested_term_months == null
    ? 'Срок не указан'
    : `${app.server.requested_term_months} мес.`;
const applicationLink = (app: Application) =>
  app.status === 'DRAFT' ? `/client/new/${app.id}` : `/client/applications/${app.id}`;
const applicationDate = (app: Application) => Date.parse(app.server?.application_date ?? '');

/** Format the calendar date locally for this page; do not change shared cards. */
function registrationDate(value: string) {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:T.*)?$/.exec(value);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : value;
}

export function ClientHome({ children }: { children: ReactNode }) {
  const state = useCredit();
  const { session } = useSession();
  const company = state.companies.find((c) => c.id === session?.profile);
  const applications = state.applications
    .filter((a) => a.companyId === session?.profile)
    .slice()
    .sort((a, b) => {
      const difference = applicationDate(b) - applicationDate(a);
      return Number.isFinite(difference) ? difference : 0;
    });
  const active =
    applications.find((a) => !['DRAFT', 'CANCELLED', 'REJECTED'].includes(a.status)) ??
    applications[0];
  const draft = applications.find((a) => a.status === 'DRAFT');
  const requests = applications
    .flatMap((app) =>
      (app.server?.requests ?? [])
        .filter((request) => request.request_status === 'OPEN')
        .map((request) => ({ app, request })),
    )
    .sort((a, b) => {
      const difference =
        Date.parse(a.request.requested_at ?? '') - Date.parse(b.request.requested_at ?? '');
      return Number.isFinite(difference) ? difference : 0;
    });
  const firstRequest = requests[0];

  return (
    <div className="client-home">
      {active ? (
        <HeroPanel>
          <p className="hero-eyebrow">Заявка № {active.id}</p>
          <h1>
            {active.server?.offer_stale
              ? 'Проверяем предложение повторно'
              : (titles[displayStatus(active)] ?? 'Рассматриваем заявку')}
            <br />
            {amount(active)}
          </h1>
          <div className="hero-bottom">
            <p>
              Запрошенные условия: {products[active.product]} · {term(active)}.
              {active.server?.purpose?.trim() && <> Цель: {active.server.purpose}.</>}
              <br />
              {httpClientStatus(active).happening}
            </p>
            <div className="actions">
              <Action tone="white" asChild>
                <Link to={applicationLink(active)}>Открыть заявку</Link>
              </Action>
            </div>
          </div>
          <div className="client-home-stages">
            <StageTrack app={active} />
          </div>
          <p className="hero-next">{httpClientStatus(active).next}</p>
        </HeroPanel>
      ) : (
        <EmptyState title="Дайте бизнесу больше возможностей">
          <p>Начните с суммы и цели. Реквизиты поможем заполнить.</p>
          <Action asChild>
            <Link to="/client/products">Подать заявку</Link>
          </Action>
        </EmptyState>
      )}

      <div className={`home-grid client-home-grid ${draft ? '' : 'without-assistant'}`}>
        {firstRequest ? (
          <Card className="dark action-card">
            <p className="attention-text">● Нужен ваш ответ</p>
            <h2>{firstRequest.request.question_text}</h2>
            <p className="small muted">Заявка № {firstRequest.app.id}</p>
            {requests.length > 1 && (
              <p className="muted">
                Ещё {counted(requests.length - 1, ['запрос', 'запроса', 'запросов'])}
              </p>
            )}
            <Action asChild>
              <Link to={`/client/applications/${firstRequest.app.id}`}>
                Ответить банку <ArrowUpRight aria-hidden size={18} />
              </Link>
            </Action>
          </Card>
        ) : (
          <Card className="dark action-card">
            <ShieldCheck aria-hidden size={28} />
            <h2>Бизнесу — следующий шаг</h2>
            <p className="muted">
              Заявка, решение и условия в одном месте. Вы контролируете каждый этап.
            </p>
            {active && <StatusBadge app={active} />}
          </Card>
        )}

        {draft && (
          <Card className="assistant-teaser">
            <h3>
              <span className="assistant-icon">
                <MessageCircle aria-hidden size={20} />
              </span>
              Помощник с заявкой
            </h3>
            <p className="muted">
              Опишите, на что нужны деньги. Помощник предложит данные для заполнения черновика — вы
              проверите и подтвердите изменения.
            </p>
            <Action tone="soft" asChild>
              <Link to={`/client/applications/${draft.id}`}>
                Продолжить с помощником <ArrowUpRight aria-hidden size={18} />
              </Link>
            </Action>
          </Card>
        )}

        {company?.server ? (
          <CompanyCard company={{ ...company, registered: registrationDate(company.registered) }} />
        ) : (
          <Card>
            <h3>Ваш бизнес</h3>
            <p className="muted">Данные компании недоступны.</p>
          </Card>
        )}
      </div>

      <Card className="client-home-applications">
        <h2>Ваши заявки</h2>
        {applications.length ? (
          applications.map((app) => (
            <div className="product-row" key={app.id}>
              <div>
                <Link to={applicationLink(app)}>
                  № {app.id} · {products[app.product]}
                </Link>
                <p>
                  Запрошено: {amount(app)} · {term(app)}
                </p>
              </div>
              <div className="application-progress">
                <StatusBadge app={app} />
                <StageTrack app={app} mini />
              </div>
            </div>
          ))
        ) : (
          <p>Пока нет заявок.</p>
        )}
      </Card>
      {children}
    </div>
  );
}
