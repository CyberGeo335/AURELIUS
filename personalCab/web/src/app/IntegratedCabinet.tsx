import { useEffect, useRef, useState } from 'react';
import { HttpV2Api, type StateV2, type ViewV2, type RecoveredOperationV2 } from '../api/HttpV2Api';
import { QuestionnaireV2, VerifyFieldV2 } from './CaseFormsV2';
import { Action, Card, ErrorState } from '../components/v2/primitives';
import { Brand } from '../components/v2/Brand';
import {
  ServerNavigation,
  ServerPage,
  WizardNavigation,
  DocumentCoverage,
  AuditJournal,
  ReviewEvidence,
  OfferComparison,
  type ServerRoute,
} from './ServerPages';
const api = new HttpV2Api();
type RequestDraft = {
  base_version: number;
  legal_form: string;
  inn: string;
  amount: string;
  term: string;
  purpose: string;
  need: string;
};
type PendingAction = {
  request_id: string;
  kind?: string;
  case_id?: string;
  expected_version?: number;
  command?: {
    request_id: string;
    action: string;
    case_id?: string;
    expected_version: number;
    text?: string;
    arguments?: Record<string, unknown>;
  };
  [key: string]: unknown;
};
const formValues = (view: ViewV2): RequestDraft => ({
  base_version: view.version,
  legal_form: String(view.request.legal_form ?? ''),
  inn: String(view.request.inn ?? ''),
  amount: String(view.request.amount_rub ?? ''),
  term: String(view.request.term_months ?? ''),
  purpose: String(view.request.purpose ?? ''),
  need: String(view.request.financing_need ?? ''),
});
const requestPatch = (draft: RequestDraft) => ({
  ...(draft.legal_form ? { legal_form: draft.legal_form } : {}),
  ...(draft.inn ? { inn: draft.inn } : {}),
  amount_rub: Number(draft.amount),
  term_months: Number(draft.term),
  purpose: draft.purpose,
  ...(draft.need ? { financing_need: draft.need } : {}),
});
const money = (value: string) =>
  Number(value).toLocaleString('ru-RU', { style: 'currency', currency: 'RUB' });
const scopes: Record<string, string> = {
  EVIDENCE_COLLECTION: 'Получение данных и документов',
  CREDIT_ASSESSMENT: 'Оценка моделью',
  BANK_STATUS: 'Получение статуса рассмотрения',
  APPLICATION_SUBMISSION: 'Подача и принятие предложения DEMO',
  DEMO_EXECUTION: 'Симуляция исполнения',
};
const statuses: Record<string, string> = {
  DRAFT: 'Черновик',
  NEEDS_INFO: 'Нужны данные',
  CHECKING: 'Проверяем',
  MANUAL_REVIEW: 'Ручное рассмотрение',
  OFFERED: 'Предложение DEMO',
  ACCEPTED: 'Предложение принято',
  EXECUTED_DEMO: 'Исполнено · DEMO',
  CANCELLED: 'Отменено',
  DECLINED: 'Отказ',
};
export function IntegratedCabinet({ route }: { route?: ServerRoute } = {}) {
  const [state, setState] = useState<StateV2 | null>(null),
    [loaded, setLoaded] = useState(false),
    [error, setError] = useState(''),
    [requestBusy, setBusy] = useState(false),
    [selected, setSelected] = useState(
      new URLSearchParams(window.location.search).get('case') ?? '',
    ),
    [text, setText] = useState('');
  const [tab, setTab] = useState('Заявки'),
    [chat, setChat] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, RequestDraft>>({});
  const [versionConflict, setVersionConflict] = useState(false);
  const [syncError, setSyncError] = useState('');
  const [lastSync, setLastSync] = useState<string | null>(null);
  const [recovered, setRecovered] = useState<RecoveredOperationV2[]>([]);
  const [recoveryReady, setRecoveryReady] = useState(false);
  const [reviewPreview, setReviewPreview] = useState<{
    caseId: string;
    version: number;
    arguments: Record<string, unknown>;
    result: {
      offer?: import('../api/HttpV2Api').OfferV2;
      decision: string;
      reason: string;
      revision: number;
    };
  } | null>(null);
  const uncertain = useRef(false);
  const pending = useRef<PendingAction | null>(null);
  const epoch = useRef(0);
  const readSequence = useRef(0);
  const identity = useRef<string | null>(null);
  const active = route
    ? state?.cases.find((c) => c.case_id === route.caseId)
    : (state?.cases.find((c) => c.case_id === selected) ?? state?.cases[0]);
  const wizard = !!route?.path.startsWith('/client/new/');
  const showRequest = !wizard || route?.step === 0;
  const showEvidence = !wizard || route?.step === 1 || route?.step === 3;
  const showConsent = !wizard || route?.step === 2 || route?.step === 3;
  const showResult = !wizard || route?.step === 3;
  const busy = requestBusy || (!!state && !recoveryReady);
  const values = active ? (drafts[active.case_id] ?? formValues(active)) : null;
  const editRequest = (field: keyof RequestDraft, value: string) => {
    if (!active) return;
    setDrafts((current) => ({
      ...current,
      [active.case_id]: { ...formValues(active), ...current[active.case_id], [field]: value },
    }));
  };
  const clearSession = () => {
    epoch.current++;
    readSequence.current++;
    identity.current = null;
    pending.current = null;
    setState(null);
    setSelected('');
    setText('');
    setChat(false);
    setTab('Заявки');
    setDrafts({});
    setVersionConflict(false);
    setError('');
    setBusy(false);
    setRecovered([]);
    setRecoveryReady(false);
    uncertain.current = false;
    setSyncError('');
    setLastSync(null);
    setReviewPreview(null);
    window.history.replaceState(null, '', window.location.pathname);
  };
  const acceptState = (next: StateV2) => {
    const changed = identity.current !== next.session.login;
    if (identity.current && identity.current !== next.session.login) clearSession();
    identity.current = next.session.login;
    setState(next);
    setSyncError('');
    setLastSync(new Date().toISOString());
    if (changed) void restoreOperations(next.session.login);
  };
  const restoreOperations = async (login: string) => {
    const generation = epoch.current;
    setRecoveryReady(false);
    try {
      const items = await api.operations();
      if (generation === epoch.current && identity.current === login) {
        setRecovered(items);
        setRecoveryReady(true);
      }
    } catch {
      if (generation === epoch.current)
        setSyncError('Не удалось восстановить незавершённые операции. Повторите синхронизацию.');
    }
  };
  useEffect(() => {
    if (active && !route) window.history.replaceState(null, '', '?case=' + active.case_id);
  }, [active?.case_id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!route || !state) return;
    const bank = state.session.role === 'OPERATOR';
    if (
      route.path === '/' ||
      (bank && route.path.startsWith('/client')) ||
      (!bank && route.path.startsWith('/bank'))
    ) {
      const oldCase = new URLSearchParams(window.location.search).get('case');
      route.navigate(
        oldCase
          ? (bank ? '/bank' : '/client') + '/applications/' + oldCase
          : bank
            ? '/bank'
            : '/client',
      );
    }
  }, [route?.path, state?.session.login]); // eslint-disable-line react-hooks/exhaustive-deps
  const refresh = async () => {
    const generation = epoch.current;
    const sequence = ++readSequence.current;
    const next = await api.state(route?.caseId, !!route && route.path !== '/client/documents');
    if (generation === epoch.current && sequence === readSequence.current) acceptState(next);
    setLoaded(true);
    return next;
  };
  useEffect(() => {
    void api
      .session()
      .then(refresh)
      .catch((e) => {
        if ((e as { status?: number }).status !== 401) setSyncError((e as Error).message);
        setLoaded(true);
      });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- Restore once; polling handles subsequent state.
  useEffect(() => {
    if (route && state) void refresh().catch((e) => setSyncError((e as Error).message));
  }, [route?.caseId, route?.path]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!state) return;
    let live = true;
    const generation = epoch.current;
    const timer = setInterval(() => {
      const sequence = ++readSequence.current;
      void api
        .state(route?.caseId, !!route && route.path !== '/client/documents')
        .then((next) => {
          if (live && generation === epoch.current && sequence === readSequence.current)
            acceptState(next);
        })
        .catch((e) => {
          if (live && generation === epoch.current && (e as { status?: number }).status === 401) {
            clearSession();
          } else if (live && generation === epoch.current) {
            setSyncError('Не удалось обновить данные. Показано последнее полученное состояние.');
          }
        });
    }, 5000);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [state?.session.login, route?.caseId, route?.path]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (body: unknown): Promise<boolean> => {
    if (busy) return false;
    if (
      recovered.length &&
      !recovered.some((op) => op.request_id === (body as PendingAction).request_id)
    ) {
      setError('Сначала восстановите или уберите сохранённые незавершённые операции.');
      return false;
    }
    if (uncertain.current && pending.current?.request_id !== (body as PendingAction).request_id) {
      setError('Сначала восстановите незавершённый запрос. Его исход пока неизвестен.');
      return false;
    }
    const generation = epoch.current;
    setBusy(true);
    setError('');
    setVersionConflict(false);
    const requestBody = {
      ...(body as Record<string, unknown>),
      request_id: (body as Record<string, unknown>).request_id ?? crypto.randomUUID(),
    } as PendingAction;
    pending.current = requestBody;
    try {
      await api.prepare(requestBody);
      if (generation !== epoch.current) return false;
      const response = await api.action(requestBody);
      if (generation !== epoch.current) return false;
      await api.acknowledge(requestBody.request_id).catch(() => {});
      if (generation !== epoch.current) return false;
      uncertain.current = false;
      setRecovered((items) => items.filter((op) => op.request_id !== requestBody.request_id));
      pending.current = null;
      if (!response.error_code) {
        const cmd = requestBody.command;
        if (cmd?.action === 'CHAT') setText((current) => (current === cmd.text ? '' : current));
        if (cmd?.action === 'UPDATE_REQUEST' && cmd.case_id) {
          setDrafts((current) => {
            const draft = current[cmd.case_id!];
            if (
              !draft ||
              JSON.stringify(requestPatch(draft)) !== JSON.stringify(cmd.arguments?.patch)
            )
              return current;
            const next = { ...current };
            delete next[cmd.case_id!];
            return next;
          });
        }
      }
      await refresh();
      if (generation !== epoch.current) return false;
      if (response.case_id) setSelected(response.case_id);
      if (route && requestBody.command?.action === 'CREATE' && response.case_id)
        route.navigate('/client/new/' + response.case_id);
      if (response.error_code) setError(response.message);
      return !response.error_code;
    } catch (e) {
      if (generation !== epoch.current) return false;
      if ((e as { status?: number }).status === 401 || (e as { status?: number }).status === 403) {
        // A 403 can also deny a valid user's action; only a failed session clears the UI.
        try {
          await api.session();
        } catch (sessionError) {
          if (generation === epoch.current && (sessionError as { status?: number }).status === 401)
            clearSession();
        }
        if (generation !== epoch.current) return false;
      }
      setVersionConflict((e as { code?: string }).code === 'STALE_CASE_VERSION');
      const status = (e as { status?: number }).status;
      uncertain.current = !status || status >= 500;
      if (status && status < 500) {
        await api.acknowledge(requestBody.request_id).catch(() => {});
        if (generation !== epoch.current) return false;
        setRecovered((items) => items.filter((op) => op.request_id !== requestBody.request_id));
      }
      if (
        (e as { status?: number }).status === 409 &&
        (e as { code?: string }).code !== 'STALE_CASE_VERSION'
      )
        pending.current = null;
      setError((e as Error).message);
      await refresh().catch(() => {});
      return false;
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  };
  const repeatOnCurrentVersion = async () => {
    const previous = pending.current;
    if (!previous || busy) return;
    const generation = epoch.current;
    try {
      const latest = await refresh();
      if (generation !== epoch.current || pending.current !== previous) return;
      const caseId = previous.command?.case_id ?? previous.case_id;
      const current = latest.cases.find((c) => c.case_id === caseId);
      if (!current) {
        setError('Заявка больше недоступна.');
        return;
      }
      await run({
        ...previous,
        request_id: crypto.randomUUID(),
        ...(previous.command
          ? {
              command: {
                ...previous.command,
                request_id: crypto.randomUUID(),
                expected_version: current.version,
              },
            }
          : { expected_version: current.version }),
      });
    } catch (e) {
      if (generation === epoch.current) setError((e as Error).message);
    }
  };
  const command = (
    action: string,
    arguments_: Record<string, unknown> = {},
    case_: ViewV2 | undefined = active,
  ) =>
    run({
      kind: 'command',
      command: {
        request_id: crypto.randomUUID(),
        action,
        case_id: case_?.case_id,
        expected_version: case_?.version ?? 0,
        arguments: arguments_,
      },
    });
  if (!loaded)
    return (
      <main className="shell">
        <Card>Восстанавливаем сессию…</Card>
      </main>
    );
  const synchronize = async () => {
    try {
      await refresh();
      if (identity.current) await restoreOperations(identity.current);
    } catch (e) {
      if ((e as { status?: number }).status === 401) clearSession();
      else setSyncError((e as Error).message);
    }
  };
  if (!state && syncError)
    return (
      <main className="shell">
        <Card>
          <h1>Нет соединения с кабинетом</h1>
          <ErrorState message={syncError} onRetry={() => void synchronize()} />
        </Card>
      </main>
    );
  if (!state)
    return (
      <main className="shell" style={{ maxWidth: 720, paddingTop: 60 }}>
        <Brand />
        <Card>
          <p className="eyebrow">AURELIUS · V2 · DEMO</p>
          <h1>Вход в кабинет</h1>
          <form
            className="form-fields"
            onSubmit={async (e) => {
              e.preventDefault();
              const form = new FormData(e.currentTarget);
              setBusy(true);
              try {
                await api.login(String(form.get('login')), String(form.get('password')));
                clearSession();
                setBusy(true);
                await refresh();
                setError('');
              } catch (err) {
                setError((err as Error).message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <label className="form-field">
              Логин
              <input name="login" autoComplete="username" required />
            </label>
            <label className="form-field">
              Пароль
              <input name="password" type="password" autoComplete="current-password" required />
            </label>
            <Action disabled={busy}>Войти</Action>
          </form>
          <ErrorState message={error} />
          <details>
            <summary>Демо-доступы</summary>
            <p>Клиенты: client01 / client02. Сотрудник: analyst. Пароль: Aurelius2026!</p>
            <p>Публичные синтетические доступы только этого отдельного DEMO-стенда.</p>
          </details>
        </Card>
      </main>
    );
  const bank = state.session.role === 'OPERATOR';
  const can = (action: string) => !!active?.allowed_actions?.includes(action);
  const canOperate = (kind: string) => !!active?.allowed_operations?.includes(kind);
  const currentData = active?.current_data ?? active?.data_context;
  const extra = (kind: string, data: Record<string, unknown>) =>
    run({ kind, case_id: active?.case_id, expected_version: active?.version, ...data });
  return (
    <>
      {route ? (
        <ServerNavigation
          state={state}
          busy={busy}
          logout={async () => {
            await api.logout();
            clearSession();
            route.navigate('/');
          }}
        />
      ) : (
        <header className="header">
          <div className="header-inner">
            <Brand />
            <nav aria-label="Основная навигация">
              {['Заявки', 'Документы', 'Компания', ...(bank ? ['Банк'] : [])].map((t) => (
                <button key={t} className="quiet-button" onClick={() => setTab(t)}>
                  {t}
                </button>
              ))}
            </nav>
            <span>
              {state.session.full_name} · {bank ? 'Сотрудник' : 'Клиент'}
            </span>
            <button
              onClick={async () => {
                await api.logout();
                clearSession();
              }}
            >
              Выйти
            </button>
          </div>
        </header>
      )}
      <main id="main" tabIndex={-1} className="shell" style={{ paddingTop: 32 }}>
        <p className="eyebrow">Серверный кабинет · DEMO</p>
        {!route && <h1>{bank ? 'Очередь рассмотрения' : tab}</h1>}
        <ErrorState message={syncError} onRetry={() => void synchronize()} />
        {lastSync && (
          <p className="small muted">
            Последняя синхронизация: {new Date(lastSync).toLocaleTimeString('ru-RU')}
          </p>
        )}
        {!recoveryReady && <p role="status">Восстанавливаем незавершённые операции…</p>}
        {recovered.length > 0 && (
          <Card>
            <h2>Незавершённые операции</h2>
            <p>
              Повтор проверит сохранённый результат с прежним ID. Удаление из списка не отменяет
              действие на сервере.
            </p>
            {recovered.map((op) => (
              <div key={op.request_id}>
                <p>
                  {op.body.command?.action ?? op.body.kind} ·{' '}
                  {op.body.command?.case_id ?? op.body.case_id ?? 'кабинет'} ·{' '}
                  {op.completed ? 'результат сохранён на сервере' : 'исход неизвестен'}
                </p>
                <Action
                  disabled={busy}
                  onClick={() => {
                    pending.current = op.body;
                    uncertain.current = true;
                    if (op.body.command?.text) {
                      setText(op.body.command.text);
                      setChat(true);
                    }
                    const caseId = op.body.command?.case_id ?? op.body.case_id;
                    if (caseId) setSelected(caseId);
                    void run(op.body);
                  }}
                >
                  Восстановить и повторить
                </Action>
                <button
                  disabled={busy}
                  onClick={async () => {
                    try {
                      await api.acknowledge(op.request_id);
                      setRecovered((items) =>
                        items.filter((item) => item.request_id !== op.request_id),
                      );
                      if (pending.current?.request_id === op.request_id) {
                        pending.current = null;
                        uncertain.current = false;
                        setError('');
                      }
                    } catch (e) {
                      setError((e as Error).message);
                    }
                  }}
                >
                  Убрать из восстановления
                </button>
              </div>
            ))}
          </Card>
        )}
        <ErrorState
          message={error}
          onRetry={
            versionConflict
              ? undefined
              : () => {
                  if (pending.current) void run(pending.current);
                  else void refresh();
                }
          }
        />
        {versionConflict && (
          <Card>
            <p>
              Заявка изменилась в другой сессии. Ваш ввод сохранён. Сверьте актуальные данные перед
              повтором.
            </p>
            {state.cases
              .filter(
                (c) =>
                  c.case_id === (pending.current?.command?.case_id ?? pending.current?.case_id),
              )
              .map((c) => (
                <p key={c.case_id}>
                  Текущие параметры сервера: {c.request.amount_rub ?? 'не указано'} ₽,{' '}
                  {c.request.term_months ?? 'не указан'} мес. Версия {c.version}.
                </p>
              ))}
            {(['CHAT', 'UPDATE_REQUEST'].includes(pending.current?.command?.action ?? '') ||
              ['fields', 'document'].includes(pending.current?.kind ?? '')) && (
              <Action disabled={busy} onClick={() => void repeatOnCurrentVersion()}>
                Повторить на актуальной версии
              </Action>
            )}
            <p>
              Повтор применит исходное действие. Чтобы изменить его, исправьте ввод и отправьте
              заново.
            </p>
          </Card>
        )}
        {route && !route.caseId && (
          <ServerPage
            route={route}
            state={state}
            busy={busy || bank}
            create={() => void command('CREATE', {}, undefined)}
          />
        )}
        {route?.caseId && !active && (
          <Card>
            <h1>Заявка не найдена или недоступна</h1>
          </Card>
        )}
        {wizard && route && active && <WizardNavigation route={route} />}
        {route?.caseId && active && !wizard && (
          <Card>
            <a href={bank ? '/bank' : '/client/applications'}>← К списку заявок</a>
            <h1>
              {bank ? 'Разбор заявки' : 'Заявка'} {active.case_id.slice(0, 15)}
            </h1>
            {!bank && can('UPDATE_REQUEST') && (
              <a href={'/client/new/' + active.case_id}>Открыть мастер анкеты</a>
            )}
          </Card>
        )}
        {(!route || !!active) && (
          <div className={route ? 'server-workspace' : 'two-columns'}>
            {!route && (
              <Card>
                <h2>{bank ? 'Кейсы клиентов' : 'Мои заявки'}</h2>
                {state.cases.length === 0 && <p>Заявок пока нет.</p>}
                {state.cases.map((c) => (
                  <button
                    key={c.case_id}
                    className="action action-soft"
                    style={{
                      display: 'block',
                      marginBottom: 12,
                      width: '100%',
                      height: 'auto',
                      padding: 16,
                    }}
                    onClick={() => {
                      setSelected(c.case_id);
                      window.scrollTo({ top: 0 });
                      setTab('Заявки');
                    }}
                  >
                    {c.case_id.slice(0, 15)} · {c.request.amount_rub ?? 'Сумма не указана'} ₽<br />
                    {statuses[c.status] ?? c.status}
                  </button>
                ))}
                {!bank && (
                  <Action
                    disabled={busy}
                    onClick={() =>
                      void run({
                        kind: 'command',
                        command: {
                          request_id: crypto.randomUUID(),
                          action: 'CREATE',
                          expected_version: 0,
                        },
                      })
                    }
                  >
                    Новая заявка
                  </Action>
                )}
                {tab === 'Компания' &&
                  state.companies.map((c) => (
                    <p key={c.company_id}>
                      {c.name} · ИНН {c.inn}
                    </p>
                  ))}
              </Card>
            )}
            <div>
              {active && (
                <>
                  <Card>
                    <p className="eyebrow">
                      {active.case_id} · ревизия {active.revision}
                    </p>
                    <h2>{statuses[active.status] ?? active.status}</h2>
                    <p>{active.message}</p>
                    {active.follow_ups
                      ?.filter((r) => r.status === 'OPEN')
                      .map((r) => (
                        <Card key={r.request_id}>
                          <h3>Нужен ваш ответ</h3>
                          <p>{r.reason}</p>
                          <p>
                            Срок:{' '}
                            {r.due_at ? new Date(r.due_at).toLocaleString('ru-RU') : 'не указан'}
                          </p>
                          {r.fields.map((code) => (
                            <p key={code}>
                              {r.answered_fields.includes(code) ? '✓' : 'Ожидается'} ·{' '}
                              {currentData?.questionnaire.find((q) => q.field_code === code)
                                ?.label ?? code}
                            </p>
                          ))}
                          {r.documents.map((name) => (
                            <p key={name}>
                              {r.answered_documents.includes(name) ? '✓' : 'Ожидается'} · файл{' '}
                              {name}
                            </p>
                          ))}
                        </Card>
                      ))}
                    {active.evidence_stale && (
                      <p role="status">
                        Новые сведения сохранены. Показан прежний снимок; обновите данные, повторите
                        оценку и рассмотрение. Прежнее предложение больше не действует.
                      </p>
                    )}
                    {(showRequest || (wizard && route?.step === 1)) && (
                      <Card>
                        <h3>Проверенный профиль бизнеса</h3>
                        {!bank && (
                          <>
                            <label>
                              <input
                                type="checkbox"
                                checked={
                                  !!state.grants.find(
                                    (g) =>
                                      g.scope === 'EVIDENCE_COLLECTION' &&
                                      !g.revoked &&
                                      new Date(g.expires_at) > new Date(),
                                  )
                                }
                                disabled={busy}
                                onChange={(e) =>
                                  void run({
                                    kind: 'consent',
                                    scope: 'EVIDENCE_COLLECTION',
                                    granted: e.target.checked,
                                  })
                                }
                              />
                              Разрешаю получить данные и документы компании
                            </label>
                            <Action
                              tone="soft"
                              disabled={busy || !can('LOOKUP_PROFILE')}
                              title={active.action_reasons?.LOOKUP_PROFILE}
                              onClick={() => void command('LOOKUP_PROFILE')}
                            >
                              Получить проверенную форму бизнеса
                            </Action>
                          </>
                        )}
                        {active.business_profile ? (
                          <>
                            <p>
                              На{' '}
                              {new Date(active.business_profile.decision_at).toLocaleString(
                                'ru-RU',
                              )}
                            </p>
                            {active.business_profile.verified_facts.map((f) => (
                              <p key={f.field}>
                                {f.field}: {f.value} · {f.source_ref}
                              </p>
                            ))}
                            {active.business_profile.conflicts.length > 0 && (
                              <p role="alert">
                                Конфликт источников: требуется проверка сотрудника.
                              </p>
                            )}
                            {!active.business_profile.verified_facts.length && (
                              <p>Проверенные сведения отсутствуют. Укажите форму бизнеса явно.</p>
                            )}
                          </>
                        ) : (
                          <p>
                            Проверенный профиль пока не получен. Предыдущие суммы и сроки не
                            подставляются.
                          </p>
                        )}
                      </Card>
                    )}
                    {active.data_resolution.gaps.map((g, i) => (
                      <p key={g.field + ':' + i} role="status">
                        {g.field}: {g.reason}
                      </p>
                    ))}
                    {!bank && showRequest && (
                      <form
                        key={active.case_id}
                        className="form-fields"
                        onSubmit={(e) => {
                          e.preventDefault();
                          void command(
                            'UPDATE_REQUEST',
                            {
                              patch: requestPatch(values!),
                              ...(active.request.inn && !values!.inn
                                ? { clear_fields: ['inn'] }
                                : {}),
                            },
                            { ...active, version: values!.base_version },
                          );
                        }}
                      >
                        <label className="form-field">
                          Форма бизнеса
                          <select
                            required
                            name="legal_form"
                            value={values!.legal_form}
                            disabled={busy || !can('UPDATE_REQUEST')}
                            onChange={(e) => editRequest('legal_form', e.target.value)}
                          >
                            <option value="">Укажите форму бизнеса</option>
                            {['IP', 'OOO', 'AO', 'OTHER'].map((v) => (
                              <option key={v}>{v}</option>
                            ))}
                          </select>
                        </label>
                        <label className="form-field">
                          ИНН
                          <input
                            name="inn"
                            value={values!.inn}
                            disabled={busy || !can('UPDATE_REQUEST')}
                            onChange={(e) => editRequest('inn', e.target.value)}
                            inputMode="numeric"
                          />
                        </label>
                        <label className="form-field">
                          Сумма, ₽
                          <input
                            required
                            name="amount"
                            type="number"
                            min="1"
                            step="1"
                            value={values!.amount}
                            disabled={busy || !can('UPDATE_REQUEST')}
                            onChange={(e) => editRequest('amount', e.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          Срок договора, месяцев
                          <input
                            required
                            name="term"
                            type="number"
                            min="1"
                            max="600"
                            step="1"
                            value={values!.term}
                            disabled={busy || !can('UPDATE_REQUEST')}
                            onChange={(e) => editRequest('term', e.target.value)}
                          />
                        </label>
                        <label className="form-field">
                          Цель
                          <select
                            name="purpose"
                            required
                            value={values!.purpose}
                            disabled={busy || !can('UPDATE_REQUEST')}
                            onChange={(e) => editRequest('purpose', e.target.value)}
                          >
                            <option value="">Укажите цель</option>
                            <option value="INVENTORY">Закупка товара</option>
                            <option value="WORKING_CAPITAL">Оборотные средства</option>
                            <option value="VEHICLE">Транспорт</option>
                            <option value="OTHER">Другая цель</option>
                          </select>
                        </label>
                        <label className="form-field">
                          Характер потребности
                          <select
                            name="need"
                            value={values!.need}
                            disabled={busy || !can('UPDATE_REQUEST')}
                            onChange={(e) => editRequest('need', e.target.value)}
                          >
                            <option value="">Нужно уточнить</option>
                            <option value="ONE_TIME_PURCHASE">Разовая закупка</option>
                            <option value="REPEATED_PURCHASES">Регулярные закупки</option>
                            <option value="CASH_GAP">Кассовый разрыв</option>
                            <option value="VEHICLE">Транспорт</option>
                          </select>
                        </label>
                        <Action disabled={busy || !can('UPDATE_REQUEST')}>
                          Сохранить параметры
                        </Action>
                      </form>
                    )}
                    {active.product_selection && showRequest && (
                      <div className="actions" style={{ flexWrap: 'wrap', marginTop: 16 }}>
                        {active.product_selection.candidates.map((c) => (
                          <button
                            disabled={
                              busy || bank || !can('SELECT_PRODUCT') || c.eligibility === 'NO_MATCH'
                            }
                            key={c.product_id}
                            className="action action-soft"
                            onClick={() =>
                              void command('SELECT_PRODUCT', { product_id: c.product_id })
                            }
                          >
                            {active.selected_product_id === c.product_id ? '✓ ' : ''}
                            {c.name} · {c.eligibility}
                            {!c.database_supported ? ' · нет адаптера БД' : ''}
                          </button>
                        ))}
                      </div>
                    )}
                    <p className="small muted">Подбор продукта не является одобрением кредита.</p>
                    {wizard &&
                      route?.step === 1 &&
                      (!active.data_context || active.evidence_stale) && (
                        <Card>
                          <h3>Собрать досье</h3>
                          <p>
                            После заполнения параметров и выбора продукта получите исходный снимок.
                            Затем появится адресная анкета и загрузка документов.
                          </p>
                          <Action
                            disabled={busy || !can('REFRESH_EVIDENCE')}
                            title={active.action_reasons?.REFRESH_EVIDENCE}
                            onClick={() => void command('REFRESH_EVIDENCE')}
                          >
                            Обновить данные
                          </Action>
                        </Card>
                      )}
                    {!bank && showConsent && (
                      <>
                        <h3>Разрешения на действия</h3>
                        {state.scopes.map((scope) => {
                          const grant = state.grants.find((g) => g.scope === scope);
                          const checked =
                            !!grant && !grant.revoked && Date.parse(grant.expires_at) > Date.now();
                          return (
                            <label key={scope} style={{ display: 'block', marginBottom: 12 }}>
                              <input
                                type="checkbox"
                                checked={checked}
                                disabled={busy}
                                onChange={(e) =>
                                  void run({ kind: 'consent', scope, granted: e.target.checked })
                                }
                              />{' '}
                              {scopes[scope]}
                              {checked
                                ? ' · до ' + new Date(grant.expires_at).toLocaleTimeString('ru-RU')
                                : ''}
                            </label>
                          );
                        })}
                        <p className="small muted">
                          Согласия действуют час и могут быть отозваны. Сообщение в чате не выдаёт
                          разрешение.
                        </p>
                        <div className="actions" style={{ flexWrap: 'wrap' }}>
                          {[
                            ['REFRESH_EVIDENCE', 'Обновить данные'],
                            ['ASSESS', 'Запустить оценку'],
                            ['SUBMIT', 'Передать на рассмотрение'],
                            ['POLL_STATUS', 'Обновить рассмотрение'],
                          ].map(([a, l]) => (
                            <Action
                              key={a}
                              tone="soft"
                              disabled={busy || !can(a)}
                              title={active.action_reasons?.[a]}
                              onClick={() => void command(a)}
                            >
                              {l}
                            </Action>
                          ))}
                          <button
                            disabled={busy || !can('CANCEL')}
                            onClick={() => void command('CANCEL')}
                          >
                            Отменить обращение
                          </button>
                        </div>
                        {['REFRESH_EVIDENCE', 'ASSESS', 'SUBMIT', 'POLL_STATUS']
                          .filter((a) => !can(a))
                          .map((a) => (
                            <p className="small muted" key={a}>
                              {
                                (
                                  {
                                    REFRESH_EVIDENCE: 'Обновление данных',
                                    ASSESS: 'Оценка',
                                    SUBMIT: 'Передача на рассмотрение',
                                    POLL_STATUS: 'Статус рассмотрения',
                                  } as Record<string, string>
                                )[a]
                              }
                              : {active.action_reasons?.[a] ?? 'Действие недоступно.'}
                            </p>
                          ))}
                      </>
                    )}
                    {active.assessment && showResult && (
                      <Card>
                        <h3>Результат оценки</h3>
                        <p>{active.assessment.status}</p>
                        <p>
                          {active.assessment.probability == null
                            ? 'Вероятность не рассчитана'
                            : `Вероятность: ${active.assessment.probability.toLocaleString('ru-RU', { style: 'percent', maximumFractionDigits: 2 })} · ${active.assessment.kind ?? ''}`}
                        </p>
                        <p>
                          Горизонт:{' '}
                          {active.assessment.horizon_months == null
                            ? 'не определён — оценка отсутствует'
                            : `${active.assessment.horizon_months} мес`}
                          .
                        </p>
                        <p>
                          Цель модели: {active.assessment.target ?? 'не определена'}. Модель:{' '}
                          {active.assessment.model_id ?? 'нет результата'}, реестр:{' '}
                          {active.assessment.registry_version ?? 'не определён'}.
                        </p>
                        {active.assessment.model_sha256 && (
                          <p>Версия артефакта: {active.assessment.model_sha256}</p>
                        )}
                        {active.assessment.reasons?.map((reason) => (
                          <p key={reason}>
                            {(
                              {
                                VERIFIED_FEATURE_INPUT_REQUIRED:
                                  'Нужны проверенные сотрудником входы модели.',
                                PRODUCT_OR_MODEL_UNSUPPORTED:
                                  'Для этого продукта нет применимой модели.',
                                MODEL_REGISTRY_UNAVAILABLE:
                                  'Реестр модели недоступен. Повторите позже.',
                                SYNTHETIC_MODEL_REQUIRES_MANUAL_REVIEW:
                                  'Синтетическая модель DEMO: требуется ручное решение сотрудника.',
                                FEATURE_REQUEST_MISMATCH:
                                  'Входы модели не соответствуют текущим параметрам заявки.',
                                FEATURE_SUBJECT_MISMATCH: 'Входы относятся к другой форме бизнеса.',
                              } as Record<string, string>
                            )[reason] ?? `Причина: ${reason}`}
                          </p>
                        ))}
                        <p>
                          Оценка DEMO не валидирована для реального кредитования. Объяснения
                          факторов
                          {active.assessment.explanations?.length ||
                          active.assessment.explanation?.status === 'AVAILABLE'
                            ? ' приведены из результата модели ниже.'
                            : ' не предоставлены.'}
                        </p>
                        {active.assessment.explanations?.map((e) => (
                          <p key={e.feature}>
                            {e.feature}: {e.contribution} · {e.source_ref ?? 'источник не указан'}
                          </p>
                        ))}
                        {active.assessment.explanation?.status === 'AVAILABLE' && (
                          <Card>
                            <h4>
                              Вклад факторов в логит месяца{' '}
                              {active.assessment.explanation.month_on_book}
                            </h4>
                            <p>
                              {active.assessment.explanation.method} ·{' '}
                              {active.assessment.explanation.space}
                            </p>
                            <p>{active.assessment.explanation.note}</p>
                            <p>Источник входов: {active.assessment.explanation.source_ref}</p>
                            <details>
                              <summary>Показать факторы модели</summary>
                              <table>
                                <thead>
                                  <tr>
                                    <th>Фактор</th>
                                    <th>Вклад в логит</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {active.assessment.explanation.contributions?.map((c) => (
                                    <tr key={c.feature}>
                                      <td>{c.feature}</td>
                                      <td>{c.contribution.toFixed(5)}</td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                              <p>
                                Базовое значение:{' '}
                                {active.assessment.explanation.base_value?.toFixed(5)} · итоговый
                                логит: {active.assessment.explanation.raw_output?.toFixed(5)}
                              </p>
                            </details>
                          </Card>
                        )}
                        {active.assessment.explanation?.status === 'UNAVAILABLE' && (
                          <p role="status">
                            Объяснение факторов временно недоступно. Фактическая оценка сохранена.
                          </p>
                        )}
                        {!!active.assessment.hazards?.length && (
                          <details>
                            <summary>Вероятности события по месяцам модели</summary>
                            {active.assessment.hazards.map((v, i) => (
                              <p key={i}>
                                Месяц {i + 1}: {(v * 100).toFixed(2)}%
                              </p>
                            ))}
                          </details>
                        )}
                        {active.assessment.calculation?.status ===
                          'ILLUSTRATIVE_EXPLICIT_INPUTS' && (
                          <Card>
                            <h4>Расчёт по проверенным входам</h4>
                            <p>
                              Платёж: {active.assessment.calculation.monthly_payment_rub} ₽ · DSCR:{' '}
                              {active.assessment.calculation.dscr ?? 'не рассчитан'}
                            </p>
                            <p>
                              Основание: {active.assessment.calculation.source_ref} ·{' '}
                              {active.assessment.calculation.formula_version}
                            </p>
                            <p>Порог решения не применялся.</p>
                          </Card>
                        )}
                      </Card>
                    )}
                    {active.bank_application && showResult && (
                      <Card>
                        <h3>Рассмотрение</h3>
                        <p>{active.bank_application.review_reasons.join('; ')}</p>
                        {active.bank_application.offer && (
                          <>
                            <p>
                              {active.bank_application.offer.amount_rub} ₽ /{' '}
                              {active.bank_application.offer.term_months} мес. /{' '}
                              {Number(active.bank_application.offer.annual_rate_fraction) * 100}%
                              годовых
                            </p>
                            <p>
                              Комиссии:{' '}
                              {active.bank_application.offer.fees_rub.length
                                ? active.bank_application.offer.fees_rub.map(money).join(' + ')
                                : money('0')}
                            </p>
                            <p>
                              До{' '}
                              {new Date(active.bank_application.offer.expires_at).toLocaleString(
                                'ru-RU',
                              )}
                              . Условия:{' '}
                              {active.bank_application.offer.conditions.join('; ') ||
                                'нет дополнительных условий'}
                            </p>
                            <p>
                              Исполнение:{' '}
                              {active.bank_application.offer.repayment_type === 'LIMIT_ONLY'
                                ? 'открытие лимита'
                                : 'выдача DEMO'}
                            </p>
                            <details>
                              <summary>График платежей</summary>
                              <table>
                                <thead>
                                  <tr>
                                    <th>Месяц</th>
                                    <th>Платёж</th>
                                    <th>Проценты</th>
                                    <th>Основной долг</th>
                                    <th>Остаток</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {active.bank_application.offer.schedule.map((r) => (
                                    <tr key={r.month}>
                                      {[r.month, r.payment, r.interest, r.principal, r.balance].map(
                                        (v, i) => (
                                          <td key={i}>{v}</td>
                                        ),
                                      )}
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </details>
                            {!bank && ['OFFERED', 'ACCEPTED'].includes(active.status) && (
                              <form
                                onSubmit={(e) => {
                                  e.preventDefault();
                                  void command(
                                    active.status === 'OFFERED' ? 'ACCEPT_OFFER' : 'EXECUTE_DEMO',
                                    {
                                      offer_id: active.bank_application!.offer!.offer_id,
                                      acknowledge_demo: true,
                                    },
                                  );
                                }}
                              >
                                <label>
                                  <input type="checkbox" required /> Подтверждаю{' '}
                                  {active.status === 'OFFERED'
                                    ? 'принятие предложения'
                                    : 'симуляцию исполнения'}{' '}
                                  · DEMO
                                </label>
                                <Action
                                  disabled={
                                    busy ||
                                    !can(
                                      active.status === 'OFFERED' ? 'ACCEPT_OFFER' : 'EXECUTE_DEMO',
                                    )
                                  }
                                >
                                  {active.status === 'OFFERED'
                                    ? 'Принять предложение DEMO'
                                    : 'Исполнить DEMO'}
                                </Action>
                              </form>
                            )}
                          </>
                        )}
                        {active.bank_application.execution && (
                          <p>Подтверждено: {active.bank_application.execution.kind} · имитация</p>
                        )}
                        {!bank &&
                          active.status === 'EXECUTED_DEMO' &&
                          active.selected_product_id === 'term' &&
                          active.bank_application.offer?.fees_rub.every((f) => Number(f) === 0) && (
                            <form
                              onSubmit={(e) => {
                                e.preventDefault();
                                const f = new FormData(e.currentTarget);
                                void extra('payment', {
                                  operation_id: crypto.randomUUID(),
                                  amount_rub: String(f.get('payment')),
                                });
                              }}
                            >
                              <label className="form-field">
                                Сумма платежа DEMO, ₽
                                <input
                                  type="number"
                                  name="payment"
                                  min="0.01"
                                  step="0.01"
                                  required
                                />
                              </label>
                              <label>
                                <input type="checkbox" required /> Подтверждаю имитацию платежа,
                                реальные деньги не переводятся
                              </label>
                              <Action disabled={busy || !canOperate('payment')}>
                                Имитировать платёж
                              </Action>
                            </form>
                          )}
                      </Card>
                    )}
                    {showResult && <OfferComparison view={active} />}
                  </Card>
                  {(active.data_context || active.current_data) && showEvidence && (
                    <Card>
                      <h2>Анкета и документы</h2>
                      <p>
                        Снимки:{' '}
                        {Object.values(active.data_context?.snapshot_ids ?? {}).join(', ') ||
                          'ещё не созданы'}
                        . {active.data_context?.model_readiness}
                      </p>
                      <details>
                        <summary>Замечания к данным</summary>
                        {active.data_context?.data_quality.blocking_issues.map((v) => (
                          <p key={v}>{v}</p>
                        ))}
                      </details>
                      <p>
                        Последние сохранённые ответы и файлы показаны ниже. Снимок выше используется
                        для оценки и остаётся неизменяемым.
                      </p>
                      <QuestionnaireV2
                        key={active.case_id + ':questionnaire'}
                        questions={currentData?.questionnaire ?? []}
                        version={active.version}
                        editable={!bank && canOperate('fields')}
                        busy={busy}
                        save={(answers, version) =>
                          run({
                            kind: 'fields',
                            case_id: active.case_id,
                            expected_version: version,
                            answers,
                          })
                        }
                      />
                      {currentData?.documents?.map((d) => (
                        <DocumentCoverage key={d.document_id} document={d} />
                      ))}
                      {!bank && (
                        <label className="form-field">
                          Добавить документ
                          <input
                            type="file"
                            accept=".csv,.xlsx,.pdf,.png,.jpg"
                            disabled={busy || !canOperate('document')}
                            onChange={async (e) => {
                              const file = e.target.files?.[0];
                              if (!file) return;
                              if (file.size > 20 * 1024 * 1024) {
                                setError('Максимальный размер 20 МБ');
                                return;
                              }
                              const data = await new Promise<string>((resolve, reject) => {
                                const reader = new FileReader();
                                reader.onload = () => resolve(String(reader.result).split(',')[1]);
                                reader.onerror = reject;
                                reader.readAsDataURL(file);
                              });
                              void extra('document', { filename: file.name, content_base64: data });
                            }}
                          />
                        </label>
                      )}
                    </Card>
                  )}
                  {bank && (
                    <Card key={active.case_id + ':operator'}>
                      <h2>Действия сотрудника</h2>
                      <p>
                        Вводы модели и источники проверяются явно. Клиентские права не позволяют
                        выполнить эти действия.
                      </p>
                      <ReviewEvidence
                        key={active.case_id + ':evidence'}
                        view={active}
                        login={state.session.login}
                        busy={busy}
                        save={(kind, arguments_) => extra(kind, { arguments: arguments_ })}
                      />
                      <form
                        onSubmit={async (e) => {
                          e.preventDefault();
                          const f = new FormData(e.currentTarget);
                          try {
                            if (!canOperate('features')) return;
                            void extra('features', {
                              arguments: JSON.parse(String(f.get('features'))),
                            });
                          } catch {
                            setError('Неверный JSON входов модели');
                          }
                        }}
                      >
                        <label className="form-field">
                          Проверенные входы модели (JSON FeatureInput)
                          <textarea name="features" rows={5} required />
                        </label>
                        <Action disabled={busy || !canOperate('features')}>
                          Сохранить проверенные входы
                        </Action>
                      </form>
                      <VerifyFieldV2
                        key={active.case_id + ':verify'}
                        questions={currentData?.questionnaire ?? []}
                        version={active.version}
                        enabled={canOperate('verify')}
                        busy={busy}
                        save={(arguments_, version) =>
                          run({
                            kind: 'verify',
                            case_id: active.case_id,
                            expected_version: version,
                            arguments: arguments_,
                          })
                        }
                      />
                      <form
                        onSubmit={async (e) => {
                          e.preventDefault();
                          const f = new FormData(e.currentTarget);
                          if (!canOperate('review')) return;
                          let offer;
                          let followUp;
                          if (f.get('decision') === 'REQUEST_DATA') {
                            const requested_fields = f.getAll('requestedField').map(String);
                            const requested_documents = String(f.get('requestedDocuments') ?? '')
                              .split('\n')
                              .map((s) => s.trim())
                              .filter(Boolean);
                            const due = new Date(String(f.get('dueAt') ?? ''));
                            if (!requested_fields.length && !requested_documents.length) {
                              setError('Выберите поля или укажите имена файлов дозапроса.');
                              return;
                            }
                            if (!Number.isFinite(due.getTime()) || due.getTime() <= Date.now()) {
                              setError('Укажите будущий срок ответа на дозапрос.');
                              return;
                            }
                            followUp = {
                              requested_fields,
                              requested_documents,
                              due_at: due.toISOString(),
                            };
                          }
                          if (f.get('decision') === 'OFFERED') {
                            if (
                              [
                                'offerAmount',
                                'offerTerm',
                                'offerRate',
                                'offerExpiry',
                                'offerFees',
                              ].some((k) => !String(f.get(k) ?? '').trim())
                            ) {
                              setError(
                                'Укажите все условия предложения, включая комиссии (0, если их нет).',
                              );
                              return;
                            }
                            const expiry = new Date(String(f.get('offerExpiry')));
                            if (!Number.isFinite(expiry.getTime())) {
                              setError('Укажите срок действия предложения');
                              return;
                            }
                            offer = {
                              amount_rub: String(f.get('offerAmount')),
                              term_months: Number(f.get('offerTerm')),
                              annual_rate_fraction: String(Number(f.get('offerRate')) / 100),
                              expires_at: expiry.toISOString(),
                              repayment_type:
                                active.selected_product_id === 'term' ? 'ANNUITY' : 'LIMIT_ONLY',
                              fees_rub:
                                Number(f.get('offerFees')) === 0
                                  ? []
                                  : [String(f.get('offerFees'))],
                              conditions: String(f.get('offerConditions'))
                                .split('\n')
                                .filter(Boolean),
                            };
                          }
                          const arguments_ = {
                            decision: f.get('decision'),
                            reason: f.get('reason'),
                            offer,
                            ...followUp,
                          };
                          if (route) {
                            setBusy(true);
                            setError('');
                            setReviewPreview(null);
                            try {
                              const result = await api.preview({
                                case_id: active.case_id,
                                expected_version: active.version,
                                arguments: arguments_,
                              });
                              setReviewPreview({
                                caseId: active.case_id,
                                version: active.version,
                                arguments: arguments_,
                                result,
                              });
                            } catch (err) {
                              setError((err as Error).message);
                            } finally {
                              setBusy(false);
                            }
                          } else void extra('review', { arguments: arguments_ });
                        }}
                      >
                        <label className="form-field">
                          Решение
                          <select name="decision">
                            <option value="REQUEST_DATA">Запросить данные</option>
                            <option value="OFFERED">Предложить условия DEMO</option>
                            <option value="DECLINED">Отказать</option>
                          </select>
                        </label>
                        <label className="form-field">
                          Обоснование
                          <textarea name="reason" required minLength={15} />
                        </label>
                        <details>
                          <summary>Поля и документы дозапроса</summary>
                          {currentData?.questionnaire
                            .filter((q) => q.editable)
                            .map((q) => (
                              <label key={q.field_code} style={{ display: 'block' }}>
                                <input
                                  type="checkbox"
                                  name="requestedField"
                                  value={q.field_code}
                                  disabled={busy || !canOperate('review')}
                                />
                                {q.label}
                              </label>
                            ))}
                          <label className="form-field">
                            Имена запрашиваемых файлов (по одному в строке)
                            <textarea
                              name="requestedDocuments"
                              disabled={busy || !canOperate('review')}
                            />
                          </label>
                          <label className="form-field">
                            Ответить до
                            <input
                              type="datetime-local"
                              name="dueAt"
                              disabled={busy || !canOperate('review')}
                            />
                          </label>
                        </details>
                        <details>
                          <summary>Условия предложения DEMO</summary>
                          <label className="form-field">
                            Сумма предложения, ₽
                            <input
                              name="offerAmount"
                              type="number"
                              min="1"
                              defaultValue={String(active.request.amount_rub ?? '')}
                            />
                          </label>
                          <label className="form-field">
                            Срок предложения, месяцев
                            <input
                              name="offerTerm"
                              type="number"
                              min="1"
                              max="600"
                              defaultValue={String(active.request.term_months ?? '')}
                            />
                          </label>
                          <label className="form-field">
                            Ставка предложения, % годовых
                            <input name="offerRate" type="number" min="0" max="100" step="0.01" />
                          </label>
                          <label className="form-field">
                            Комиссии, ₽ (явно укажите 0, если нет)
                            <input name="offerFees" type="number" min="0" step="0.01" />
                          </label>
                          <label className="form-field">
                            Действует до
                            <input name="offerExpiry" type="datetime-local" />
                          </label>
                          <label className="form-field">
                            Дополнительные условия, каждое с новой строки
                            <textarea name="offerConditions" />
                          </label>
                          <p>
                            {active.selected_product_id === 'term'
                              ? 'Аннуитетная выдача DEMO'
                              : 'Только открытие лимита DEMO'}
                          </p>
                        </details>
                        <Action disabled={busy || !canOperate('review')}>
                          {route ? 'Предпросмотр решения' : 'Сохранить решение'}
                        </Action>
                      </form>
                      {reviewPreview?.caseId === active.case_id && (
                        <Card>
                          <h3>Предпросмотр решения</h3>
                          <p>
                            {reviewPreview.result.decision} · ревизия{' '}
                            {reviewPreview.result.revision}
                          </p>
                          <p>{reviewPreview.result.reason}</p>
                          {reviewPreview.result.offer && (
                            <>
                              <p>
                                {reviewPreview.result.offer.amount_rub} ₽ ·{' '}
                                {reviewPreview.result.offer.term_months} мес. ·{' '}
                                {Number(reviewPreview.result.offer.annual_rate_fraction) * 100}%
                                годовых
                              </p>
                              <p>
                                Комиссии: {reviewPreview.result.offer.fees_rub.join(' + ') || '0'} ₽
                              </p>
                              <p>
                                Дополнительные условия:{' '}
                                {reviewPreview.result.offer.conditions.join('; ') || 'нет'}
                              </p>
                              <p>
                                До{' '}
                                {new Date(reviewPreview.result.offer.expires_at).toLocaleString(
                                  'ru-RU',
                                )}
                              </p>
                            </>
                          )}
                          {reviewPreview.version !== active.version && (
                            <p role="alert">Заявка изменилась. Сформируйте предпросмотр заново.</p>
                          )}
                          <Action
                            disabled={
                              busy ||
                              !canOperate('review') ||
                              reviewPreview.version !== active.version
                            }
                            onClick={async () => {
                              const saved = await run({
                                kind: 'review',
                                case_id: active.case_id,
                                expected_version: reviewPreview.version,
                                arguments: reviewPreview.arguments,
                              });
                              if (saved) setReviewPreview(null);
                            }}
                          >
                            Подтвердить решение
                          </Action>
                        </Card>
                      )}
                    </Card>
                  )}
                  {!wizard && (
                    <Card>
                      <h2>История</h2>
                      {active.history.map((h, i) => (
                        <p key={i}>
                          <strong>{h.role === 'user' ? 'Вы' : 'Помощник'}: </strong>
                          {h.content}
                        </p>
                      ))}
                    </Card>
                  )}
                  {bank && route && (
                    <AuditJournal key={active.case_id + ':audit'} caseId={active.case_id} />
                  )}
                </>
              )}
            </div>
          </div>
        )}
        {wizard && route && active && (
          <Card>
            <div className="actions">
              {route.step > 0 && (
                <Action
                  tone="soft"
                  onClick={() => route.navigate(route.path + '?step=' + (route.step - 1))}
                >
                  Назад
                </Action>
              )}
              {route.step < 3 && (
                <Action onClick={() => route.navigate(route.path + '?step=' + (route.step + 1))}>
                  Продолжить
                </Action>
              )}
              <Action
                tone="soft"
                onClick={() => route.navigate('/client/applications/' + active.case_id)}
              >
                К состоянию заявки
              </Action>
            </div>
          </Card>
        )}
      </main>
      {!bank && (
        <>
          <button className="assistant-launcher" onClick={() => setChat(!chat)}>
            {chat ? 'Свернуть' : 'Помощник'}
          </button>
          {chat && (
            <section
              className="card integrated-chat"
              style={{
                position: 'fixed',
                right: 24,
                bottom: 90,
                width: 440,
                maxHeight: '75vh',
                overflowY: 'auto',
                zIndex: 50,
              }}
            >
              <h2>Помощник для бизнеса</h2>
              {!active ? (
                <p>Создайте заявку, чтобы начать диалог.</p>
              ) : (
                <>
                  <div aria-live="polite">
                    {active.history.slice(-8).map((h, i) => (
                      <p key={i}>{h.content}</p>
                    ))}
                  </div>
                  {active.pending && (
                    <div>
                      <blockquote>{active.pending.source_text}</blockquote>
                      <pre style={{ whiteSpace: 'pre-wrap' }}>
                        {JSON.stringify(active.pending.patch, null, 2)}
                      </pre>
                      <Action
                        disabled={busy || !can('CONFIRM_FACTS')}
                        onClick={() =>
                          void command('CONFIRM_FACTS', {
                            proposal_id: active.pending!.proposal_id,
                          })
                        }
                      >
                        Да, верно
                      </Action>
                    </div>
                  )}
                  {active.last_knowledge_answer && (
                    <details>
                      <summary>Источники справки</summary>
                      <p>Версия {active.last_knowledge_answer.source_sha256.slice(0, 12)}</p>
                      {active.last_knowledge_answer.citations.map((c) => (
                        <p key={c.field_code}>
                          {c.field_code}: {c.format_rule}
                          <br />
                          {c.source_ref}
                        </p>
                      ))}
                    </details>
                  )}
                  <form
                    onSubmit={(e) => {
                      e.preventDefault();
                      const body = {
                        kind: 'command',
                        command: {
                          request_id: crypto.randomUUID(),
                          action: 'CHAT',
                          case_id: active.case_id,
                          expected_version: active.version,
                          text,
                        },
                      };
                      void run(body);
                    }}
                  >
                    <label className="form-field">
                      Сообщение
                      <textarea
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        required
                        maxLength={12000}
                      />
                    </label>
                    <Action disabled={busy || !can('CHAT')}>
                      {busy ? 'Помощник отвечает…' : 'Отправить'}
                    </Action>
                  </form>
                </>
              )}
            </section>
          )}
        </>
      )}
      <footer className="shell footer">
        AURELIUS · Отдельный серверный DEMO. Реальные подпись и переводы не выполняются.
      </footer>
    </>
  );
}
