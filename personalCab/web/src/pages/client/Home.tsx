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
export function ProductList() {
  const api = useApi();
  const { session } = useSession();
  const nav = useNavigate();
  const action = useAction();
  return (
    <Card className="products">
      <ErrorState message={action.error} />
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
export function Home({ onAssistant }: { onAssistant: () => void }) {
  const { session } = useSession();
  const state = useCredit();
  const company = state.companies.find((c) => c.id === session!.profile)!;
  const apps = state.applications.filter((a) => a.companyId === company.id);
  const app =
    apps.find((a) => !['CANCELLED', 'DECLINED', 'FUNDED_DEMO', 'DRAFT'].includes(a.status)) ??
    apps[0];
  const nav = useNavigate();
  const responseApp = apps.find(
    (a) => a.status === 'NEEDS_INFO' && a.requests.some((r) => r.state === 'OPEN'),
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
            {titles[app.status] ?? 'Проверяем заявку на'}
            <br />
            {money(app.amount)}
          </h1>
          <div className="hero-bottom">
            <p>
              {products[app.product]} на {app.term} месяцев, на {app.purpose.toLowerCase()}.<br />
              {app.status === 'NEEDS_INFO'
                ? 'Нужно уточнение, чтобы продолжить проверку.'
                : app.externalWait && app.status === 'CHECKING'
                  ? 'Ожидаем внешний источник. Сбой не означает отказ.'
                  : 'Все этапы и условия — в карточке заявки.'}
            </p>
            <div className="actions">
              <Action tone="white" asChild>
                <Link
                  to={
                    app.status === 'DRAFT'
                      ? `/client/new/${app.id}`
                      : `/client/applications/${app.id}`
                  }
                >
                  Открыть заявку
                </Link>
              </Action>
              <Action tone="outline" asChild>
                <Link to={`/client/applications/${app.id}#history`}>Что проверяет банк</Link>
              </Action>
            </div>
          </div>
          <StageTrack app={app} />
        </HeroPanel>
      ) : (
        <EmptyState title="Дайте бизнесу больше возможностей">
          <p>Начните с суммы и цели. Реквизиты поможем заполнить.</p>
        </EmptyState>
      )}
      <div className="home-grid">
        {responseApp ? (
          <Card className="dark action-card">
            <p className="attention-text">● Нужен ваш ответ</p>
            <h2>{responseApp.requests.find((r) => r.state === 'OPEN')!.text}</h2>
            <p className="small muted">Заявка {responseApp.id}</p>
            <p className="muted">
              Уточните данные, и банк продолжит проверку этой заявки. История сохранится.
            </p>
            <Action onClick={() => nav(`/client/applications/${responseApp.id}`)}>
              Ответить банку <ArrowUpRight aria-hidden size={18} />
            </Action>
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
                {a.id} · ревизия {a.revision}
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
                to={a.status === 'DRAFT' ? `/client/new/${a.id}` : `/client/applications/${a.id}`}
              >
                Открыть
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
