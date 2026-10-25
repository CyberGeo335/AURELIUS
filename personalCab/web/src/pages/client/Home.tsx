import { BusinessHome } from '../../business/BusinessPages';
import { displayStatus } from '../../domain/status';
import { Link, useNavigate } from 'react-router';
import { Plus, ArrowUpRight, ShieldCheck } from 'lucide-react';
import { useApi, useCredit, useSession, useAction } from '../../app/context';
import {
  Action,
  Card,
  CompanyCard,
  AssistantTeaser,
  HeroPanel,
  StageTrack,
  StatusBadge,
  EmptyState,
  ErrorState,
} from '../../components/v2/primitives';
import { products, type Product } from '../../domain/types';
import { money } from '../../domain/finance';
import { datetime, date } from '../../domain/finance';
import { clientStatus } from '../../domain/clientStatus';
export function ProductList() {
  const api = useApi();
  const { session } = useSession();
  const nav = useNavigate();
  const action = useAction();
  return (
    <Card className="products">
      <ErrorState message={action.error} onRetry={action.retry} />
      {(Object.entries(products) as [Product, string][]).map(([code, name]) => (
        <div className="product-row" key={code}>
          <div>
            <h2>{name}</h2>
            <span className="small muted">{code} · Демо-условия</span>
          </div>
          <p className="muted">
            {code === 'R01'
              ? 'Без залога, на товар и текущие расходы. До 5 млн ₽, 3–24 месяца.'
              : code === 'R02'
                ? 'Лимит, который берёте частями, когда нужно.'
                : 'Платежи сверх остатка, пока выручка в пути.'}
          </p>
          <Action
            disabled={action.busy}
            onClick={() =>
              action.run(async () =>
                nav('/client/new/' + (await api.createDraft(session!.profile, code))),
              )
            }
          >
            Новая заявка <Plus aria-hidden size={18} />
          </Action>
        </div>
      ))}
    </Card>
  );
}
function MockHome({ onAssistant }: { onAssistant: () => void }) {
  const api = useApi();
  const responseAction = useAction();
  const { session } = useSession();
  const state = useCredit();
  const company = state.companies.find((c) => c.id === session!.profile)!;
  const apps = state.applications.filter((a) => a.companyId === company.id);
  const app =
    apps.find(
      (a) => !['CANCELLED', 'DECLINED', 'FUNDED_DEMO', 'DRAFT'].includes(displayStatus(a)),
    ) ?? apps[0];
  const nav = useNavigate();
  const responseApp = apps.find(
    (a) => displayStatus(a) === 'NEEDS_INFO' && a.requests.some((r) => r.state === 'OPEN'),
  );
  const titles: Record<string, string> = {
    NEEDS_INFO: 'Проверяем заявку на',
    MANUAL_REVIEW: 'Специалист проверяет',
    OFFERED: 'Ваше предложение готово',
    FUNDED_DEMO: 'Деньги на счёте',
    DRAFT: 'Продолжим вашу заявку',
    DECLINED: 'Решение по заявке',
    CANCELLED: 'Заявка отменена',
    ACCEPTED: 'Осталось подписать',
    SIGNED_DEMO: 'Договор подписан',
  };
  return (
    <>
      {app ? (
        <HeroPanel>
          <p className="hero-eyebrow">Заявка {app.id} · демо-кабинет</p>
          <h1>
            {titles[displayStatus(app)] ?? 'Проверяем заявку на'}
            <br />
            {money(app.amount)}
          </h1>
          <div className="hero-bottom">
            <p>
              {products[app.product]} на {app.term} месяцев. Цель: {app.purpose.toLowerCase()}.
              <br />
              {displayStatus(app) === 'NEEDS_INFO'
                ? 'Нужно уточнение, чтобы продолжить проверку.'
                : app.externalWait && displayStatus(app) === 'CHECKING'
                  ? 'Ожидаем внешний источник. Сбой не означает отказ.'
                  : 'Все этапы и условия — в карточке заявки.'}
            </p>
            <div className="actions">
              <Action tone="white" asChild>
                <Link
                  to={
                    displayStatus(app) === 'DRAFT'
                      ? `/client/new/${app.id}`
                      : `/client/applications/${app.id}`
                  }
                >
                  Открыть заявку
                </Link>
              </Action>
              <Action tone="outline" asChild>
                <Link to={`/client/applications/${app.id}#history`}>Что дальше</Link>
              </Action>
            </div>
          </div>
          <StageTrack app={app} />
          <p className="hero-next">{clientStatus(app).next}</p>
        </HeroPanel>
      ) : (
        <EmptyState title="Дайте бизнесу больше возможностей">
          <p>Начните с суммы и цели. Реквизиты поможем заполнить.</p>
        </EmptyState>
      )}
      <div className="home-grid">
        {responseApp ? (
          <Card className="dark action-card">
            <ErrorState message={responseAction.error} onRetry={responseAction.retry} />
            <p className="attention-text">● Нужен ваш ответ</p>
            <h2>{responseApp.requests.find((r) => r.state === 'OPEN')!.text}</h2>
            <p className="small muted">Заявка {responseApp.id}</p>
            <p className="muted">
              {responseApp.requests.find((r) => r.state === 'OPEN')?.reason ??
                'Уточните платёж, чтобы банк правильно рассчитал нагрузку на бизнес.'}{' '}
              Ответьте до{' '}
              {date(
                responseApp.requests.find((r) => r.state === 'OPEN')?.dueAt ??
                  responseApp.created + 3 * 86400000,
              )}
              .
            </p>
            <Action onClick={() => nav(`/client/applications/${responseApp.id}`)}>
              Ответить банку <ArrowUpRight aria-hidden size={18} />
            </Action>
            {responseApp.requests.find((r) => r.state === 'OPEN')?.field === 'leasing' && (
              <div className="actions">
                <Action
                  tone="soft"
                  disabled={responseAction.busy}
                  onClick={() =>
                    responseAction.run(() =>
                      api.answerRequest(
                        responseApp.id,
                        responseApp.requests.find((r) => r.state === 'OPEN')!.id,
                        'Да, это лизинг',
                      ),
                    )
                  }
                >
                  Да, это лизинг
                </Action>
                <Action
                  tone="outline"
                  disabled={responseAction.busy}
                  onClick={() =>
                    responseAction.run(() =>
                      api.answerRequest(
                        responseApp.id,
                        responseApp.requests.find((r) => r.state === 'OPEN')!.id,
                        'Нет, это другой платёж',
                      ),
                    )
                  }
                >
                  Нет, другое
                </Action>
              </div>
            )}
          </Card>
        ) : (
          <Card className="dark action-card">
            <ShieldCheck aria-hidden size={28} />
            <h2>Бизнесу — следующий шаг</h2>
            <p className="muted">
              Заявка, понятное решение и условия в одном месте. Вы контролируете каждый этап.
            </p>
            {app && <StatusBadge app={app} />}
          </Card>
        )}
        <AssistantTeaser onOpen={onAssistant} />
        <CompanyCard company={company} />
      </div>
      <ProductList />
    </>
  );
}
export function Applications() {
  const { session } = useSession();
  const state = useCredit();
  const apps = state.applications.filter((a) => a.companyId === session!.profile);
  return (
    <>
      <div className="page-title">
        <h1>Мои заявки</h1>
        <Action asChild>
          <Link to="/client/products">
            Новая заявка <Plus aria-hidden size={18} />
          </Link>
        </Action>
      </div>
      {apps.length ? (
        apps.map((a) => (
          <Card key={a.id} className="application-row">
            <div>
              <p className="small muted">
                {a.id} · {datetime(a.updated)}
              </p>
              <h2>{money(a.amount)}</h2>
              <p>
                {products[a.product]} · {a.term} мес.
              </p>
            </div>
            <div className="application-progress">
              <StatusBadge app={a} />
              <StageTrack app={a} mini />
            </div>
            <Action tone="ink" asChild>
              <Link
                to={
                  displayStatus(a) === 'DRAFT'
                    ? `/client/new/${a.id}`
                    : `/client/applications/${a.id}`
                }
              >
                {displayStatus(a) === 'DRAFT' ? 'Продолжить' : 'Открыть'}
              </Link>
            </Action>
          </Card>
        ))
      ) : (
        <EmptyState title="Заявок пока нет">
          <p>Выберите продукт и расскажите о бизнесе.</p>
        </EmptyState>
      )}
    </>
  );
}

export function Home(props: { onAssistant: () => void }) {
  return import.meta.env.VITE_API_MODE === 'http' ? <BusinessHome /> : <MockHome {...props} />;
}
