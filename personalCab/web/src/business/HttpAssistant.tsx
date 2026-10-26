import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useLocation } from 'react-router';
import { ChevronDown, MessageCircle, X } from 'lucide-react';
import { useApi, useCredit, useSession } from '../app/context';
import { HttpCreditApi } from '../api/HttpCreditApi';
import { Action, Card, ErrorState } from '../components/v2/primitives';
import { Textarea } from '../components/ui/textarea';
import { products, type Application, type Product } from '../domain/types';
import { assistantLabels } from './assistantLabels';
import { ProductTerms } from './ProductTerms';

const AssistantContext = createContext<(id?: string | null) => void>(() => {});
export const useHttpAssistant = () => useContext(AssistantContext);

export function AssistantDraftCard({ app }: { app: Application }) {
  const open = useHttpAssistant();
  return (
    <Card>
      <h2>Ассистент по заявке</h2>
      <p className="muted">
        Помощник предложит сведения для этой заявки. Изменения сохраняются только после вашего
        подтверждения.
      </p>
      <Action tone="soft" onClick={() => open(app.id)}>
        Открыть помощника
      </Action>
    </Card>
  );
}

/** No browser transcript: history and proposals come exclusively from /api/v2/state. */
export function HttpAssistantProvider({ children }: { children: ReactNode }) {
  const api = useApi() as HttpCreditApi;
  const state = useCredit();
  const { session } = useSession();
  const { pathname } = useLocation();
  const eligible =
    import.meta.env.VITE_API_MODE === 'http' &&
    session?.role === 'client' &&
    /^\/client(?:\/|$)/.test(pathname);
  const [open, setOpen] = useState(false);
  const [selection, setSelection] = useState<{ path: string; id: string | null } | null>(null);
  // Unsaved input is ephemeral, separated by draft; never persist customer messages locally.
  const [texts, setTexts] = useState<Record<string, string>>({});
  const [errors, setErrors] = useState<
    Record<string, { message: string; retryChat: boolean } | undefined>
  >({});
  const [busy, setBusy] = useState(false);
  const locked = useRef(false);
  const launcher = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const scroll = useRef<HTMLDivElement>(null);
  const proposal = useRef<HTMLDivElement>(null);
  const own = state.applications.filter((a) => a.companyId === session?.profile);
  const latest = own
    .filter((a) => a.status === 'DRAFT')
    .sort(
      (a, b) =>
        Date.parse(b.server?.application_date ?? '') -
          Date.parse(a.server?.application_date ?? '') || Number(b.id) - Number(a.id),
    )[0];
  const pathId = pathname.match(/^\/client\/(?:applications|new)\/([^/]+)\/?$/)?.[1];
  const pathDraft = own.find((a) => a.id === pathId && a.status === 'DRAFT');
  const bound = own.find((a) => a.id === selection?.id);
  const app =
    selection?.path === pathname
      ? bound
      : (pathDraft ?? (bound && bound.status !== 'DRAFT' ? bound : latest));
  const context = app?.id ?? 'new';
  const text = texts[context] ?? '';
  const editable = !app || app.status === 'DRAFT';
  const dialogue = app?.server?.dialogue;
  const catalog = (state.catalog ?? []).filter((row) =>
    ['R01', 'R02', 'R03'].includes(String(row.product_code)),
  );
  const pending = dialogue?.pending;
  const proposalId = pending?.proposal_id;

  const show = (id?: string | null) => {
    const target = id === undefined ? (pathDraft ?? latest) : own.find((a) => a.id === id);
    setSelection({ path: pathname, id: target?.id ?? null });
    setOpen(true);
  };
  const close = () => {
    setOpen(false);
    launcher.current?.focus();
  };
  useEffect(() => {
    if (!eligible || !open) return;
    (
      panel.current?.querySelector<HTMLElement>('textarea:not(:disabled)') ??
      panel.current?.querySelector<HTMLElement>('a, button')
    )?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        setOpen(false);
        launcher.current?.focus();
      }
    };
    window.addEventListener('keydown', keydown);
    return () => window.removeEventListener('keydown', keydown);
  }, [eligible, open, context]);

  useEffect(() => {
    if (open && scroll.current) {
      scroll.current.scrollTop =
        proposalId && proposal.current
          ? proposal.current.offsetTop
          : context !== 'new'
            ? scroll.current.scrollHeight
            : 0;
    }
  }, [open, context, dialogue?.history.length, proposalId]);

  const run = async (operation: (setErrorContext: (key: string) => void) => Promise<void>) => {
    if (locked.current) return;
    locked.current = true;
    setBusy(true);
    let errorContext = context;
    setErrors((old) => ({ ...old, [context]: undefined }));
    try {
      await operation((key) => {
        errorContext = key;
      });
    } catch (error) {
      const e = error as { code?: string; message?: string };
      const message =
        e.code === 'EXTRACTION_UNAVAILABLE'
          ? 'Помощник не смог разобрать сообщение — повторите или заполните форму'
          : (e.message ?? 'Не удалось выполнить действие. Повторите попытку.');
      setErrors((old) => ({
        ...old,
        [errorContext]: { message, retryChat: e.code === 'EXTRACTION_UNAVAILABLE' },
      }));
    } finally {
      locked.current = false;
      setBusy(false);
    }
  };
  const send = () => {
    if (!app || app.status !== 'DRAFT' || !text.trim()) return;
    const id = app.id;
    void run(async () => {
      await api.command('chat', id, { text });
      setTexts((old) => ({ ...old, [id]: '' }));
    });
  };
  const create = (product: Product) =>
    void run(async (setErrorContext) => {
      const id = await api.createDraft(session!.profile, product);
      setErrorContext(id);
      setTexts((old) => ({ ...old, [id]: text, new: '' }));
      setSelection({ path: pathname, id });
      if (text.trim()) {
        await api.command('chat', id, { text });
        setTexts((old) => ({ ...old, [id]: '' }));
      }
    });

  return (
    <AssistantContext value={show}>
      {children}
      {eligible && (
        <>
          <button
            ref={launcher}
            type="button"
            id="assistant-launcher"
            className="assistant-launcher"
            aria-label={open ? 'Свернуть чат с помощником' : 'Открыть чат с помощником'}
            aria-expanded={open}
            aria-controls="http-assistant-chat"
            onClick={() => (open ? close() : selection ? setOpen(true) : show())}
          >
            {open ? <ChevronDown aria-hidden size={21} /> : <MessageCircle aria-hidden size={21} />}
            <span>{open ? 'Свернуть' : 'Помощник'}</span>
          </button>
          <section
            ref={panel}
            id="http-assistant-chat"
            className="http-assistant"
            role="dialog"
            aria-modal="false"
            aria-labelledby="http-assistant-title"
            hidden={!open}
          >
            <header className="http-assistant-header">
              <h2 id="http-assistant-title">Помощник с заявкой</h2>
              <button type="button" aria-label="Закрыть помощника" onClick={close}>
                <X aria-hidden size={20} />
              </button>
            </header>
            <div className="http-assistant-context">
              {app ? (
                <>
                  <strong>
                    Заявка № {app.id} · {products[app.product]}
                  </strong>
                  <Link to={`/client/applications/${app.id}`}>Открыть заявку</Link>
                </>
              ) : (
                <strong>Новая заявка</strong>
              )}
            </div>
            <div ref={scroll} className="http-assistant-scroll">
              {!app && (
                <>
                  <p>Опишите, на что нужны деньги — помогу оформить заявку</p>
                  <p className="small muted">
                    Выберите продукт из каталога. Заявка появится только после нажатия «Создать
                    заявку».
                  </p>
                  {catalog.map((row) => (
                    <div className="inset" key={String(row.terms_id)}>
                      <ProductTerms row={row} />
                      <Action
                        disabled={busy}
                        tone="soft"
                        onClick={() => create(row.product_code as Product)}
                      >
                        Создать заявку: {products[row.product_code as Product]}
                      </Action>
                    </div>
                  ))}
                  {!catalog.length && <p>Каталог недоступен. Попробуйте обновить страницу.</p>}
                </>
              )}
              {app && (
                <>
                  <p className="small muted">
                    Предложенные сведения меняют анкету только после явного подтверждения. Согласия
                    и отправка заявки — отдельные действия.
                  </p>
                  <div className="http-assistant-messages" aria-label="Диалог по заявке">
                    {dialogue?.history.map((message, index) => (
                      <div
                        className={`inset ${message.role === 'user' ? 'from-client' : ''}`}
                        key={index}
                      >
                        <strong>{message.role === 'user' ? 'Вы' : 'Ассистент'}</strong>
                        <p>{message.content}</p>
                      </div>
                    ))}
                    {!dialogue?.history.length && <p className="muted">Сообщений пока нет.</p>}
                  </div>
                  {editable && pending && (
                    <div ref={proposal} className="inset">
                      <h3>Предложенные сведения</h3>
                      <dl>
                        {Object.entries(pending.patch).map(([field, value]) => (
                          <div key={field}>
                            <dt>{assistantLabels[field] ?? field}</dt>
                            <dd>{pending.display_values?.[field] ?? String(value)}</dd>
                            {pending.quotes[field] && (
                              <dd className="small muted">
                                Из сообщения: «{pending.quotes[field]}»
                              </dd>
                            )}
                          </div>
                        ))}
                      </dl>
                      <Action
                        disabled={busy}
                        onClick={() =>
                          void run(async () => {
                            await api.command('confirm_facts', app.id, {
                              proposal_id: pending.proposal_id,
                            });
                          })
                        }
                      >
                        Подтвердить предложенные изменения
                      </Action>
                    </div>
                  )}
                  {!editable && (
                    <p role="status">
                      Помощник меняет только черновики. История этой заявки доступна только для
                      чтения.
                    </p>
                  )}
                  <div className="http-assistant-actions">
                    <Action tone="outline" disabled={busy} onClick={() => show(null)}>
                      Новая заявка с помощником
                    </Action>
                    <Link
                      to={editable ? `/client/new/${app.id}` : `/client/applications/${app.id}`}
                      onClick={close}
                    >
                      {editable ? 'Заполнить форму' : 'Посмотреть заявку'}
                    </Link>
                  </div>
                </>
              )}
            </div>
            {busy && (
              <p role="status" className="assistant-typing">
                Помощник думает, это может занять несколько минут
              </p>
            )}
            <ErrorState message={editable ? (errors[context]?.message ?? '') : ''} />
            {editable && app && errors[context]?.retryChat && (
              <div className="http-assistant-actions">
                <Action tone="soft" disabled={busy || !text.trim()} onClick={send}>
                  Повторить сообщение
                </Action>
                <Link to={`/client/new/${app.id}`} onClick={close}>
                  Продолжить через форму
                </Link>
              </div>
            )}
            {editable && (
              <div className="http-assistant-composer">
                <label className="form-field">
                  Расскажите о потребности
                  <Textarea
                    maxLength={12000}
                    disabled={busy}
                    value={text}
                    onChange={(event) =>
                      setTexts((old) => ({ ...old, [context]: event.target.value }))
                    }
                  />
                </label>
                {app ? (
                  <Action disabled={busy || !text.trim()} onClick={send}>
                    Отправить сообщение
                  </Action>
                ) : (
                  <p className="small muted">
                    Сообщение отправится после создания выбранной заявки.
                  </p>
                )}
              </div>
            )}
          </section>
        </>
      )}
    </AssistantContext>
  );
}
