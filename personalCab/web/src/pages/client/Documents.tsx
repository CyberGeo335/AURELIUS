import { displayStatus } from '../../domain/status';
import { Link } from 'react-router';
import {
  FileText,
  FileCheck2,
  ShieldCheck,
  FolderOpen,
  ArrowUpRight,
  Check,
  Clock3,
} from 'lucide-react';
import { useCredit, useSession } from '../../app/context';
import { Action, Card, EmptyState, StatusBadge } from '../../components/v2/primitives';
import { Disclosure } from '../../components/v2/Disclosure';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from '../../components/ui/dialog';
import type { Application } from '../../domain/types';
import { counted } from '../../domain/text';
import { date, datetime, money } from '../../domain/finance';
function ConsentRow({ app, kind }: { app: Application; kind: 'bki' | 'data' }) {
  const received = kind === 'bki' ? app.consentBki : app.consentData;
  const label = kind === 'bki' ? 'Кредитная история' : 'Обработка данных';
  return (
    <div className="consent-row">
      <span className={`consent-symbol ${received ? 'received' : ''}`}>
        {received ? <Check aria-hidden size={18} /> : <Clock3 aria-hidden size={18} />}
      </span>
      <div>
        <strong>{label}</strong>
        <p className="small muted">
          {received
            ? 'Согласие получено'
            : app.companyId === 'zerno' && kind === 'bki'
              ? 'Согласие даст руководитель'
              : 'Ожидает подтверждения'}
          {received && app.consentedAt ? ` · ${date(app.consentedAt)}` : ''}
        </p>
      </div>
      <Dialog>
        <DialogTrigger asChild>
          <button className="quiet-button" aria-label={`Подробнее: ${label.toLowerCase()}`}>
            Подробнее
          </button>
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{label}</DialogTitle>
            <DialogDescription>
              {kind === 'bki'
                ? 'Разрешение на запрос кредитной истории для рассмотрения этой заявки.'
                : 'Обработка сведений, которые вы предоставили в анкете.'}
            </DialogDescription>
          </DialogHeader>
          <p>
            {received
              ? 'Получено отдельно от диалога с помощником. Сообщение в чате не считается согласием.'
              : 'Подтвердить согласие можно на соответствующем шаге анкеты.'}
          </p>
          <dl className="details">
            <dt>Заявка</dt>
            <dd>{app.id}</dd>
            <dt>Версия текста</dt>
            <dd>
              {kind === 'bki'
                ? (app.consentVersion ?? 'bki-demo-2026.10-v1')
                : 'data-demo-2026.10-v1'}
            </dd>
            <dt>Дата</dt>
            <dd>{app.consentedAt ? datetime(app.consentedAt) : 'Ещё не подтверждено'}</dd>
          </dl>
          <p className="small muted">
            На демо-стенде реальные запросы и юридически значимые действия не выполняются.
          </p>
        </DialogContent>
      </Dialog>
    </div>
  );
}
export function ApplicationDocuments({
  app,
  compact = false,
}: {
  app: Application;
  compact?: boolean;
}) {
  const openRequest = app.requests.find((r) => r.state === 'OPEN');
  const destination =
    displayStatus(app) === 'DRAFT' ? `/client/new/${app.id}` : `/client/applications/${app.id}`;
  return (
    <div className={`application-documents ${compact ? 'compact' : ''}`}>
      <section>
        <div className="section-caption">
          <FileText aria-hidden size={19} />
          <h3>Файлы</h3>
          <span className="count-chip">{app.files.length}</span>
        </div>
        {app.files.length ? (
          <ul className="file-list">
            {app.files.map((file, i) => (
              <li key={`${file}-${i}`}>
                <span className="document-icon">
                  <FileCheck2 aria-hidden size={21} />
                </span>
                <div>
                  <strong>{file}</strong>
                  <p className="small muted">
                    Добавлен к заявке · {file.split('.').at(-1)?.toUpperCase()}
                  </p>
                </div>
                <span className="status status-OFFERED">Добавлен</span>
              </li>
            ))}
          </ul>
        ) : (
          <div className="document-empty">
            <FolderOpen aria-hidden size={29} />
            <strong>Файлов пока нет</strong>
            <p className="muted small">
              {['ACCEPTED', 'SIGNED_DEMO', 'FUNDED_DEMO', 'DECLINED', 'CANCELLED'].includes(
                displayStatus(app),
              )
                ? 'Вы не добавляли файлы к этой заявке.'
                : 'Если для проверки понадобится документ, здесь появится запрос банка.'}
            </p>
            {(openRequest || displayStatus(app) === 'DRAFT') && (
              <Action tone="soft" asChild>
                <Link to={destination}>
                  {openRequest ? 'Ответить на запрос' : 'Продолжить анкету'}
                  <ArrowUpRight aria-hidden size={17} />
                </Link>
              </Action>
            )}
          </div>
        )}
      </section>
      <section>
        <div className="section-caption">
          <ShieldCheck aria-hidden size={19} />
          <h3>Согласия</h3>
        </div>
        <ConsentRow app={app} kind="bki" />
        <ConsentRow app={app} kind="data" />
      </section>
    </div>
  );
}
export function Documents() {
  const state = useCredit();
  const { session } = useSession();
  const apps = state.applications.filter((a) => a.companyId === session!.profile);
  if (import.meta.env.VITE_API_MODE === 'http')
    return (
      <Card>
        <h1>Документы заявок</h1>
        <p>Загруженные документы сохранены без проверки содержания.</p>
        {apps.map((app) => (
          <div className="inset" key={app.id}>
            <Link to={`/client/applications/${app.id}`}>Заявка № {app.id}</Link>
            {app.server?.documents?.map((document) => (
              <p key={document.document_id}>
                <a href={`/api/v2/documents/${document.document_id}`} download>
                  {document.filename}
                </a>{' '}
                · Сохранён, не проверен
              </p>
            ))}
            {!app.server?.documents?.length && <p className="muted">Документов пока нет.</p>}
          </div>
        ))}
        {!apps.length && <p>Пока нет заявок.</p>}
      </Card>
    );
  const count = apps.reduce((n, a) => n + a.files.length, 0);
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">Ваш кабинет</p>
          <h1>Документы и согласия</h1>
          <p className="muted">Всё, что вы передали по заявке, и подтверждённые разрешения.</p>
        </div>
        <span className="document-total">
          <FileText aria-hidden size={20} />
          {counted(count, ['файл', 'файла', 'файлов'])} ·{' '}
          {counted(apps.length, ['заявка', 'заявки', 'заявок'])}
        </span>
      </div>
      {apps.length ? (
        apps.map((app) => (
          <Card className="documents-card" key={app.id}>
            <div className="documents-heading">
              <div>
                <p className="small muted">{app.id}</p>
                <h2>
                  {money(app.amount)} <span>на {app.term} мес.</span>
                </h2>
              </div>
              <StatusBadge app={app} />
              <Action tone="soft" asChild>
                <Link
                  to={
                    displayStatus(app) === 'DRAFT'
                      ? `/client/new/${app.id}`
                      : `/client/applications/${app.id}`
                  }
                >
                  Открыть заявку <ArrowUpRight aria-hidden size={17} />
                </Link>
              </Action>
            </div>
            <ApplicationDocuments app={app} />
            <Disclosure
              title="Как хранятся документы на демо-стенде"
              description="Что сохраняется и где посмотреть подтверждение"
            >
              <p className="small muted">
                Файл остаётся на вашем устройстве. В кабинете сохраняются его имя и отметка о
                добавлении. Реальные договоры и электронные подписи на демо-стенде не создаются.
              </p>
            </Disclosure>
          </Card>
        ))
      ) : (
        <EmptyState title="Здесь будут документы ваших заявок">
          <p>Начните заявку самостоятельно или подберите продукт с помощником.</p>
          <Action asChild>
            <Link to="/client/products">Подобрать продукт</Link>
          </Action>
        </EmptyState>
      )}
    </>
  );
}
