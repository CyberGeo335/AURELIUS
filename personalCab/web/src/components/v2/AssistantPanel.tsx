import { useEffect, useState, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router';
import {
  MessageCircle,
  ArrowUpRight,
  Check,
  PenLine,
  Send,
  WifiOff,
  ShieldCheck,
  LoaderCircle,
} from 'lucide-react';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '../ui/dialog';
import { Textarea } from '../ui/textarea';
import { Input } from '../ui/input';
import { Action, ErrorState } from './primitives';
import { HttpChatApi } from '../../api/HttpChatApi';
import { AssistantSessionStore, type AssistantSession } from '../../api/AssistantSession';
import { useAction, useSession, useApi, useCredit } from '../../app/context';
import { money, coverage, decimal, payment } from '../../domain/finance';
import { backendProduct } from '../../domain/products';
import { products, type Product } from '../../domain/types';
import { clientStatus } from '../../domain/clientStatus';
const chat = new HttpChatApi();
const cache = new AssistantSessionStore();
export function AssistantPanel({
  open,
  onOpenChange,
  seed,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  seed?: string;
}) {
  const { session } = useSession();
  const profile = session?.profile ?? 'karpov';
  const api = useApi();
  const state = useCredit();
  const location = useLocation();
  const nav = useNavigate();
  const action = useAction();
  const [conversation, setConversation] = useState<AssistantSession>(() => cache.read(profile));
  const [text, setText] = useState('');
  const [health, setHealth] = useState<'loading' | 'ready' | 'offline'>('loading');
  const [editing, setEditing] = useState(false);
  const [contextAnswer, setContextAnswer] = useState('');
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (open && scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [open, conversation.messages.length, action.busy]);
  const pathId = location.pathname.match(/\/(?:applications|new)\/([^/]+)/)?.[1];
  const app =
    state.applications.find(
      (a) => a.companyId === profile && a.id === (pathId ?? conversation.applicationId),
    ) ?? state.applications.find((a) => a.companyId === profile && a.status !== 'DRAFT');
  const update = (patch: Partial<AssistantSession>) =>
    setConversation((old) => {
      const next = { ...old, ...patch };
      try {
        cache.save(profile, next);
      } catch {
        action.setError('Не удалось сохранить диалог. Освободите место в браузере.');
      }
      return next;
    });
  useEffect(() => {
    setConversation(cache.read(profile));
    setContextAnswer('');
  }, [profile]);
  useEffect(() => {
    if (open && seed) setText(seed);
  }, [open, seed]);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setHealth('loading');
    void chat
      .health()
      .then((value) => {
        if (!cancelled) setHealth(value.status === 'ready' ? 'ready' : 'offline');
      })
      .catch(() => {
        if (!cancelled) setHealth('offline');
      });
    const stored = cache.read(profile);
    void chat
      .state()
      .then((remote) => {
        if (cancelled || stored.messages.length || !remote.history.length) return;
        if (stored.caseId && remote.latest?.result.case_id === stored.caseId) {
          const restored = {
            ...stored,
            messages: remote.history.map((m) => ({
              role: m.role,
              text: m.content ?? m.text ?? '',
            })),
          };
          setConversation(restored);
          cache.save(profile, restored);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [open, profile]);
  const send = () =>
    action.run(async () => {
      const pending = cache.read(profile).pending ??
        conversation.pending ?? { id: crypto.randomUUID(), text: text.trim() };
      update({ pending });
      const response = await chat.send(pending.text, pending.id);
      update({
        messages: [
          ...conversation.messages,
          { role: 'user', text: pending.text },
          { role: 'assistant', text: response.result.message ?? 'Проверьте сведения ниже.' },
        ],
        facts: response.result.request ?? {},
        quote: pending.text,
        caseId: response.result.case_id,
        candidates: response.result.product_selection?.candidates ?? [],
        pending: undefined,
        lastMessageId: pending.id,
      });
      setText('');
    });
  const amount = Number(conversation.facts.amount_rub) || undefined;
  const term = Number(conversation.facts.term_months) || undefined;
  const purpose =
    typeof conversation.facts.purpose === 'string' ? conversation.facts.purpose : undefined;
  const purposeLabels: Record<string, string> = {
    INVENTORY: 'Закупка товара',
    WORKING_CAPITAL: 'Пополнение оборотных средств',
    CASH_GAP: 'Покрытие кассового разрыва',
    SUPPLIERS: 'Оплата поставщикам',
  };
  const purposeLabel = purpose ? (purposeLabels[purpose] ?? purpose) : undefined;
  const legalForm =
    typeof conversation.facts.legal_form === 'string' ? conversation.facts.legal_form : undefined;
  const profileEntity = state.companies.find((c) => c.id === profile)?.entity;
  const legalMismatch = !!legalForm && legalForm !== profileEntity;
  const suggestedProduct = conversation.candidates
    .filter((c) => c.eligibility !== 'NO_MATCH')
    .sort((a, b) => a.priority - b.priority)
    .map((c) => backendProduct(c.product_family, c.product_id))
    .find(Boolean);
  const consentMessage = /(?:соглас|разреш).*(?:бки|кредитн.*истор)|бки.*(?:соглас|разреш)/i.test(
    text,
  );
  const factsReady = !!amount && !!term && !!purposeLabel;
  const confirmedApp = conversation.applicationId
    ? state.applications.find((a) => a.id === conversation.applicationId && a.companyId === profile)
    : undefined;
  const confirm = (product: Product) =>
    action.run(async () => {
      const id = await api.applyAssistant(profile, product, {
        amount,
        term,
        purpose: purposeLabel,
        caseId: conversation.caseId,
        messageId: `${conversation.lastMessageId ?? 'confirmed'}:${JSON.stringify([product, amount, term, purposeLabel])}`,
        applicationId: pathId ?? conversation.applicationId,
      });
      update({ applicationId: id });
      setEditing(false);
    });
  const toForm = () =>
    action.run(async () => {
      const target = confirmedApp ?? (pathId ? app : undefined);
      const id = target?.id ?? (await api.createDraft(profile, 'R01'));
      update({ applicationId: id });
      onOpenChange(false);
      nav(target && target.status !== 'DRAFT' ? `/client/applications/${id}` : `/client/new/${id}`);
    });
  const localContext = (question: 'status' | 'decision' | 'request' | 'term') => {
    if (!app) {
      setContextAnswer('Начните с задачи и суммы. Вы также можете выбрать продукт самостоятельно.');
      return;
    }
    const status = clientStatus(app);
    const answer =
      question === 'decision'
        ? app.offers[0]?.kind === 'COUNTEROFFER'
          ? `Вы запросили ${money(app.amount)} на ${app.term} мес. Покрытие исходного платежа — ${decimal(coverage(app.flow, app.existing, app.amount, app.term))}× при минимуме 1,3×. Банк предложил варианты с меньшей нагрузкой. ${app.reason}`
          : app.status === 'DECLINED'
            ? app.reason
            : app.status === 'OFFERED'
              ? 'Платёж подходит по нагрузке. Условия и причины — в вашей заявке.'
              : status.happening
        : question === 'request'
          ? (app.requests.find((r) => r.state === 'OPEN')?.text ?? status.next)
          : question === 'term'
            ? `Предварительный платёж на 18 месяцев — ${money(payment(app.offers[0]?.amount ?? app.amount, 18))}. Другой срок требует перепроверки в заявке.`
            : `${status.happening} ${status.next}`;
    setContextAnswer(answer);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange} modal={false}>
      <DialogContent
        id="assistant-chat"
        className="assistant-chat"
        onInteractOutside={(event) => event.preventDefault()}
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          inputRef.current?.focus();
        }}
        onCloseAutoFocus={(event) => {
          event.preventDefault();
          document.getElementById('assistant-launcher')?.focus();
        }}
      >
        <DialogHeader>
          <span className="assistant-label">
            <MessageCircle aria-hidden size={17} />
            Помощник для бизнеса
          </span>
          <DialogTitle>Обсудим вашу задачу</DialogTitle>
          <DialogDescription>
            Подберём продукт и поможем с заявкой. Решение принимает банк.
          </DialogDescription>
        </DialogHeader>
        <div className={`assistant-health ${health}`} role="status">
          <span />
          {health === 'loading'
            ? 'Проверяем подключение…'
            : health === 'ready'
              ? 'Ассистент доступен'
              : 'ИИ-ассистент временно недоступен'}
          {health === 'offline' && <WifiOff aria-hidden size={15} />}
        </div>
        <div className="assistant-scroll" ref={scrollRef}>
          <div className="assistant-prompts">
            {app && (
              <>
                <button onClick={() => localContext('status')}>Что сейчас происходит?</button>
                <button onClick={() => localContext('decision')}>Почему такое решение?</button>
                <button onClick={() => localContext('request')}>Что нужно от меня?</button>
                {app.status === 'OFFERED' && (
                  <button onClick={() => localContext('term')}>Что будет на 18 месяцев?</button>
                )}
              </>
            )}
          </div>
          {contextAnswer && (
            <div className="context-answer">
              <span className="small muted">По данным вашей заявки</span>
              <p>{contextAnswer}</p>
              {app?.requests.some((r) => r.state === 'OPEN') && (
                <Action
                  tone="soft"
                  onClick={() => {
                    onOpenChange(false);
                    nav(`/client/applications/${app.id}`);
                  }}
                >
                  Открыть запрос и добавить документ
                </Action>
              )}
            </div>
          )}
          {health === 'offline' && (
            <div className="assistant-unavailable">
              <h3>Продолжим через форму</h3>
              <p className="small muted">
                Подтверждённые сведения и переписка сохранены. Выберите продукт сами или
                воспользуйтесь подсказками по назначению.
              </p>
              <Action tone="soft" onClick={toForm}>
                Заполнить формой <ArrowUpRight aria-hidden size={17} />
              </Action>
            </div>
          )}
          <div className="chat-messages" aria-live="polite">
            {conversation.messages.map((m, i) => (
              <div className={`bubble ${m.role === 'user' ? 'user' : 'assistant'}`} key={i}>
                {m.text}
              </div>
            ))}
            {!conversation.messages.length && health === 'ready' && (
              <p className="muted">
                Например: «Нужно полтора миллиона на закупку товара, верну за год».
              </p>
            )}
          </div>
          {(amount || term || purpose) && (
            <div className="assistant-facts">
              <p className="eyebrow">Правильно поняли?</p>
              <blockquote>«{conversation.quote}»</blockquote>
              {legalForm && (
                <p className="small">
                  Форма бизнеса:{' '}
                  {legalForm === 'IP' ? 'ИП' : legalForm === 'OOO' ? 'ООО' : legalForm}
                </p>
              )}
              {legalMismatch && (
                <p className="field-error">
                  Форма бизнеса отличается от выбранного профиля. Поправьте её перед подтверждением.
                </p>
              )}
              {editing ? (
                <div className="form-fields">
                  <label className="form-field">
                    Форма бизнеса
                    <select
                      value={legalForm ?? profileEntity}
                      onChange={(e) =>
                        update({ facts: { ...conversation.facts, legal_form: e.target.value } })
                      }
                    >
                      <option value="IP">ИП</option>
                      <option value="OOO">ООО</option>
                    </select>
                  </label>
                  <label className="form-field">
                    Сумма, ₽
                    <Input
                      type="number"
                      value={amount ?? ''}
                      onChange={(e) =>
                        update({
                          facts: { ...conversation.facts, amount_rub: Number(e.target.value) },
                        })
                      }
                    />
                  </label>
                  <label className="form-field">
                    Срок, месяцев
                    <Input
                      type="number"
                      value={term ?? ''}
                      onChange={(e) =>
                        update({
                          facts: { ...conversation.facts, term_months: Number(e.target.value) },
                        })
                      }
                    />
                  </label>
                  <label className="form-field">
                    Цель
                    <Input
                      value={purposeLabel ?? ''}
                      onChange={(e) =>
                        update({ facts: { ...conversation.facts, purpose: e.target.value } })
                      }
                    />
                  </label>
                </div>
              ) : (
                <p>
                  <strong>{amount ? money(amount) : 'Сумма не указана'}</strong> ·{' '}
                  {term ? `${term} мес.` : 'Срок не указан'}
                  <br />
                  {purposeLabel}
                </p>
              )}
              <div className="actions">
                <Action
                  className="assistant-action"
                  disabled={action.busy || legalMismatch || !factsReady}
                  onClick={() => confirm(confirmedApp?.product ?? suggestedProduct ?? 'R01')}
                >
                  <Check aria-hidden size={17} />
                  Да, верно
                </Action>
                <button className="quiet-button" onClick={() => setEditing(!editing)}>
                  <PenLine aria-hidden size={16} />
                  Поправить
                </button>
              </div>
              <p className="small muted">
                В анкету попадут только подтверждённые данные. Согласия оформляются отдельно.
              </p>
            </div>
          )}
          {conversation.candidates.length > 0 && (
            <div className="assistant-candidates">
              <h3>Варианты для вашей задачи</h3>
              {[...conversation.candidates]
                .sort((a, b) => a.priority - b.priority)
                .map((candidate) => {
                  const code = backendProduct(candidate.product_family, candidate.product_id);
                  return (
                    <div className="assistant-candidate" key={candidate.product_id}>
                      <div className="spread">
                        <strong>{code ? products[code] : candidate.name}</strong>
                        <span
                          className={`status ${candidate.eligibility === 'MATCH' ? 'status-OFFERED' : candidate.eligibility === 'NO_MATCH' ? 'status-DECLINED' : 'status-NEEDS_INFO'}`}
                        >
                          {candidate.eligibility === 'MATCH'
                            ? 'Подходит'
                            : candidate.eligibility === 'NO_MATCH'
                              ? 'Не подходит'
                              : 'Нужно уточнить'}
                        </span>
                      </div>
                      <p className="small">{candidate.reasons.join(' ')}</p>
                      {candidate.requirements.slice(0, 3).map((r) => (
                        <p className="small muted" key={r.label}>
                          {r.label}
                        </p>
                      ))}
                      {code && (
                        <Action
                          tone="soft"
                          disabled={
                            candidate.eligibility === 'NO_MATCH' ||
                            action.busy ||
                            legalMismatch ||
                            !factsReady
                          }
                          onClick={() => confirm(code)}
                        >
                          Выбрать и подтвердить
                        </Action>
                      )}
                    </div>
                  );
                })}
              <p className="small muted">Подбор продукта — это не одобрение кредита.</p>
            </div>
          )}
          {confirmedApp && (
            <div className="assistant-linked">
              <ShieldCheck aria-hidden size={20} />
              <div>
                <strong>Заявка {confirmedApp.id}</strong>
                <p className="small muted">
                  Подтверждённые данные сохранены. Продолжите с того же места.
                </p>
                <Action
                  tone="ink"
                  onClick={() => {
                    onOpenChange(false);
                    nav(
                      confirmedApp.status === 'DRAFT'
                        ? `/client/new/${confirmedApp.id}`
                        : `/client/applications/${confirmedApp.id}`,
                    );
                  }}
                >
                  Перейти к анкете <ArrowUpRight aria-hidden size={17} />
                </Action>
              </div>
            </div>
          )}
          {!amount && conversation.messages.length > 0 && (
            <p className="small muted">Какая сумма нужна бизнесу?</p>
          )}
          {amount && !term && (
            <p className="small muted">На какой срок вы планируете взять деньги?</p>
          )}
          {amount && term && !purpose && <p className="small muted">На что нужны деньги?</p>}
        </div>
        <ErrorState message={action.error} onRetry={action.retry} />
        {consentMessage && (
          <p className="small muted">
            Сообщение не считается согласием на запрос в БКИ. Подтвердите его отдельным чекбоксом на
            шаге «Согласия» в анкете.
          </p>
        )}
        {action.busy && (
          <p className="assistant-typing" role="status">
            Помощник отвечает…
          </p>
        )}
        <div className="assistant-composer">
          <label className="form-field">
            Ваше сообщение
            <Textarea
              ref={inputRef}
              rows={2}
              maxLength={12000}
              value={conversation.pending?.text ?? text}
              disabled={action.busy || !!conversation.pending}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (
                  e.key === 'Enter' &&
                  !e.shiftKey &&
                  !e.nativeEvent.isComposing &&
                  !action.busy &&
                  ((health === 'ready' && text.trim()) || consentMessage)
                ) {
                  e.preventDefault();
                  void (consentMessage ? toForm() : send());
                }
              }}
              placeholder="Задайте вопрос…"
            />
          </label>
          <Action
            className="assistant-action assistant-send"
            aria-label={
              action.busy
                ? 'Помощник отвечает…'
                : conversation.pending
                  ? 'Повторить запрос'
                  : consentMessage
                    ? 'К согласиям в анкете'
                    : 'Отправить'
            }
            title={
              conversation.pending
                ? 'Повторить запрос'
                : consentMessage
                  ? 'К согласиям в анкете'
                  : 'Отправить · Enter'
            }
            disabled={
              action.busy ||
              (!text.trim() && !conversation.pending) ||
              (health !== 'ready' && !conversation.pending && !consentMessage)
            }
            onClick={consentMessage ? toForm : send}
          >
            {action.busy ? (
              <LoaderCircle aria-hidden className="assistant-spinner" size={20} />
            ) : (
              <Send aria-hidden size={20} />
            )}
          </Action>
        </div>
        {conversation.pending && !action.busy && (
          <button className="quiet-button" onClick={() => update({ pending: undefined })}>
            Написать другое сообщение
          </button>
        )}
      </DialogContent>
    </Dialog>
  );
}
