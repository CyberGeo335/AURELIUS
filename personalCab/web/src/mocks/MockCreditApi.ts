import { requestId } from '../domain/requestId';
import { displayStatus } from '../domain/status';
import type { CreditApi, DraftPatch } from '../api/CreditApi';
import type {
  Application,
  BankAction,
  CreditState,
  Offer,
  Product,
  Profile,
  AssistantFacts,
  RequestOptions,
} from '../domain/types';
import type { UiStatus as Status } from '../domain/status';
import { assertTransition, backendStatus, setMockStatus, type UiStatus } from '../domain/status';
import { coverage, MIN_COVERAGE } from '../domain/finance';
import { validateApplication, defaultFields } from '../domain/forms';
import { requiredChecks } from '../domain/review';
import { makeDraft, seedState } from './seeds';
export const STORAGE_KEY = 'aurelius-v2-credit-v1';
const uid = () => requestId();
export class MockCreditApi implements CreditApi {
  private state: CreditState;
  private listeners = new Set<() => void>();
  constructor(
    private storage: Storage = localStorage,
    private now = () => Date.now(),
  ) {
    this.state = this.read() ?? seedState(this.now());
    window.addEventListener('storage', this.onStorage);
  }
  destroy = () => window.removeEventListener('storage', this.onStorage);
  private read(): CreditState | undefined {
    try {
      const raw = this.storage.getItem(STORAGE_KEY);
      if (!raw) return;
      const s = JSON.parse(raw);
      if (s.version === 1 && Array.isArray(s.applications) && Array.isArray(s.companies)) {
        for (const app of s.applications) {
          if (
            app.status in backendStatus &&
            !['DRAFT', 'SUBMITTED', 'CANCELLED'].includes(app.status)
          )
            setMockStatus(app, app.status as UiStatus);
        }
        return s;
      }
    } catch {
      /* Preserve unreadable data; surface recovery through reset. */
    }
    return {
      ...seedState(this.now()),
      storageError:
        'Не удалось прочитать сохранённое демо. Разрешите локальное хранилище или сбросьте демо-данные на экране входа.',
    };
  }
  private onStorage = (event: StorageEvent) => {
    if (event.key === STORAGE_KEY) {
      this.state = this.read() ?? seedState(this.now());
      this.emit();
    }
  };
  private emit() {
    this.listeners.forEach((l) => l());
  }
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private async transaction(update: (s: CreditState) => void) {
    const execute = () => {
      const s = structuredClone(this.read() ?? this.state);
      if (s.storageError) throw new Error(s.storageError);
      update(s);
      try {
        this.storage.setItem(STORAGE_KEY, JSON.stringify(s));
      } catch {
        throw new Error('Не удалось сохранить изменения. Освободите место в браузере и повторите.');
      }
      this.state = s;
      this.emit();
    };
    if (navigator.locks) await navigator.locks.request(STORAGE_KEY, execute);
    else execute();
  }
  private app(s: CreditState, id: string) {
    const a = s.applications.find((a) => a.id === id);
    if (!a) throw new Error('Заявка не найдена');
    return a;
  }
  private log(a: Application, text: string, actor = 'Система · демо') {
    a.updated = this.now();
    a.history.unshift({
      id: uid(),
      at: this.now(),
      actor,
      text,
      revision: a.revision,
      model: 'score-model v0.3',
      policy: 'policy-2026.10',
      snapshot: `FS-${a.id}-${a.revision}`,
    });
  }
  private move(a: Application, to: Status, text: string, actor?: string) {
    assertTransition(displayStatus(a), to);
    setMockStatus(a, to);
    this.log(a, text, actor);
  }
  private snapshot(a: Application, reason: string) {
    a.revisions.push({
      revision: a.revision,
      at: this.now(),
      amount: a.amount,
      term: a.term,
      fields: { ...a.fields },
      reason,
    });
    a.revision += 1;
    a.offers = [];
    a.acceptedOffer = undefined;
  }
  private offer(
    a: Application,
    amount: number,
    term: number,
    label: string,
    kind: Offer['kind'] = 'OFFER',
  ): Offer {
    return {
      id: uid(),
      revision: a.revision,
      amount,
      term,
      label,
      kind,
      expires: this.now() + 6 * 86400000,
    };
  }
  createDraft = async (profile: Profile, product: Product) => {
    let id = '';
    await this.transaction((s) => {
      const existing = s.applications.find(
        (a) => a.companyId === profile && a.product === product && displayStatus(a) === 'DRAFT',
      );
      if (existing) {
        id = existing.id;
        return;
      }
      const c = s.companies.find((c) => c.id === profile)!;
      id = `${product}-2026-${String(152 + s.applications.length).padStart(5, '0')}`;
      const a = makeDraft(c, product, id, this.now());
      this.log(a, 'Создан черновик', 'Клиент');
      s.applications.unshift(a);
    });
    return id;
  };
  saveDraft = async (id: string, patch: DraftPatch) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) !== 'DRAFT') throw new Error('Редактировать можно только черновик.');
      if (patch.fields) {
        for (const [key, value] of Object.entries(patch.fields)) {
          if (value !== a.fields[key] && a.sources[key]?.includes('Клиент')) {
            a.originalFields ??= {};
            a.originalFields[key] ??= a.fields[key];
          }
        }
      }
      if (patch.step !== undefined) a.furthestStep = Math.max(a.furthestStep ?? a.step, patch.step);
      Object.assign(a, patch);
      a.fields[`${a.product}_05`] = String(a.amount);
      a.fields[`${a.product}_06`] = String(a.term);
      a.fields[`${a.product}_04`] = a.purpose;
      a.updated = this.now();
    });
  submit = async (id: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) !== 'DRAFT') return;
      const errors = validateApplication(
        a,
        s.companies.find((c) => c.id === a.companyId)!,
      );
      if (Object.keys(errors).length) throw new Error(Object.values(errors)[0]);
      a.consentVersion = 'bki-demo-2026.10-v1';
      a.consentedAt = this.now();
      this.move(
        a,
        'SUBMITTED',
        'Заявка отправлена. Согласия зафиксированы: bki-demo-2026.10-v1',
        'Клиент',
      );
      a.nextAt = this.now() + 1500;
    });
  revise = async (id: string, amount: number, term: number) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) !== 'OFFERED')
        throw new Error('Изменить условия можно после получения предложения.');
      if (
        !Number.isFinite(amount) ||
        amount < 100000 ||
        amount > 5000000 ||
        !Number.isInteger(term) ||
        term < 3 ||
        term > 24
      )
        throw new Error('Сумма: 100 000–5 000 000 ₽; срок: 3–24 месяца.');
      this.snapshot(a, 'Изменение суммы или срока');
      a.amount = amount;
      a.term = term;
      a.fields[`${a.product}_05`] = String(amount);
      a.fields[`${a.product}_06`] = String(term);
      a.reason = '';
      this.move(
        a,
        'CHECKING',
        'Условия изменены. Старые предложения отозваны, начата новая проверка',
        'Клиент',
      );
      a.stage = 1;
      a.nextAt = this.now() + 1800;
    });
  answerRequest = async (id: string, requestId: string, answer: string, file?: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      const request = a.requests.find((r) => r.id === requestId);
      if (!request) throw new Error('Дозапрос не найден.');
      if (request.state === 'CLOSED') return;
      if (displayStatus(a) !== 'NEEDS_INFO') throw new Error('Заявка уже не ожидает данных.');
      if (!answer.trim() && !file) throw new Error('Добавьте ответ или документ.');
      if (request.field === 'statement' && !file)
        throw new Error('Добавьте выписку в PDF или CSV.');
      if (
        request.field === 'leasing' &&
        !['Да, это лизинг', 'Нет, это другой платёж'].includes(answer)
      )
        throw new Error('Уточните тип платежа.');
      this.snapshot(a, 'Ответ на дозапрос');
      request.state = 'CLOSED';
      request.answer = answer;
      request.file = file;
      if (file) a.files.push(file);
      if (request.field === 'leasing') {
        a.leasing = answer.startsWith('Да');
        a.existing = a.leasing ? 38000 : 0;
      }
      if (request.field === 'statement') a.statement = true;
      a.externalWait = false;
      if (!a.requests.some((r) => r.state === 'OPEN')) {
        this.move(a, 'CHECKING', 'Получены дополнительные данные. Проверка продолжена', 'Клиент');
        a.stage = 1;
        a.nextAt = this.now() + 1600;
      } else this.log(a, 'Получен ответ на дозапрос', 'Клиент');
    });
  bankDecision = async (
    id: string,
    revision: number,
    action: BankAction,
    reason: string,
    request?: RequestOptions,
  ) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) !== 'MANUAL_REVIEW' || a.revision !== revision)
        throw new Error('Заявка уже изменилась. Проверьте актуальное состояние.');
      if (reason.trim().length < 15) throw new Error('Объясните решение: не менее 15 символов.');
      a.owner = 'Анна Смирнова';
      a.reason = reason.trim();
      a.nextAt = undefined;
      if (action === 'INFO') {
        if (!request || request.dueAt <= this.now())
          throw new Error('Выберите поле или документ и срок ответа.');
        a.requests.push({
          id: uid(),
          field: request.field,
          text: reason.trim(),
          reason: 'Нужно для продолжения проверки заявки',
          dueAt: request.dueAt,
          state: 'OPEN',
        });
        this.move(a, 'NEEDS_INFO', 'Запрошены данные: ' + reason, 'Анна Смирнова');
      } else if (action === 'DECLINE') {
        a.reasonCode = 'MANUAL_POLICY_DECLINE';
        this.move(a, 'DECLINED', 'Отказ: ' + reason, 'Анна Смирнова');
      } else {
        if (!requiredChecks(a).ready)
          throw new Error('Сначала завершите обязательные проверки в досье.');
        const opts = this.alternatives(a);
        a.offers = action === 'A' ? [opts[0]] : action === 'B' ? [opts[1]] : opts;
        if (a.offers.some((o) => coverage(a.flow, a.existing, o.amount, o.term) < MIN_COVERAGE))
          throw new Error(
            'Покрытие выбранного варианта ниже 1,3×. Запросите данные или выберите другой вариант.',
          );
        a.stage = 5;
        this.move(a, 'OFFERED', 'Встречное предложение: ' + reason, 'Анна Смирнова');
      }
    });
  resolveData = async (id: string, kind: 'authority' | 'revenue', comment: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) !== 'MANUAL_REVIEW')
        throw new Error('Заявка уже вышла из ручного разбора.');
      if (comment.trim().length < 10)
        throw new Error('Добавьте комментарий к проверке от 10 символов.');
      a.checks = {
        authority: a.checks?.authority ?? false,
        revenue: a.checks?.revenue ?? false,
        comment: comment.trim(),
        [kind]: true,
      };
      this.log(
        a,
        `${kind === 'authority' ? 'Подтверждены полномочия подписанта' : 'Разрешён конфликт выручки'}: ${comment}`,
        'Анна Смирнова',
      );
    });
  applyAssistant = async (profile: Profile, product: Product, facts: AssistantFacts) => {
    let id = '';
    await this.transaction((s) => {
      let a = facts.applicationId
        ? s.applications.find((a) => a.id === facts.applicationId && a.companyId === profile)
        : s.applications.find(
            (a) => a.companyId === profile && a.product === product && displayStatus(a) === 'DRAFT',
          );
      if (facts.applicationId && !a) throw new Error('Нет доступа к указанной заявке.');
      if (!a) {
        const company = s.companies.find((c) => c.id === profile)!;
        a = makeDraft(
          company,
          product,
          `${product}-2026-${String(152 + s.applications.length).padStart(5, '0')}`,
          this.now(),
        );
        s.applications.unshift(a);
      }
      id = a.id;
      if (a.assistantMessageIds?.includes(facts.messageId) && a.product === product) return;
      if (!['DRAFT', 'OFFERED'].includes(displayStatus(a)))
        throw new Error('Заявка уже проверяется. Дождитесь предложения перед изменением условий.');
      if (a.product !== product) {
        if (displayStatus(a) !== 'DRAFT')
          throw new Error('Для другого продукта начните отдельную заявку.');
        const company = s.companies.find((c) => c.id === profile)!;
        const previous = a.fields;
        const changed = defaultFields(company, product);
        for (const code of Object.keys(changed)) {
          const n = code.split('_')[1];
          if (Number(n) < 32 && ![1].includes(Number(n)) && previous[`${a.product}_${n}`])
            changed[code] = previous[`${a.product}_${n}`];
        }
        a.product = product;
        a.fields = changed;
      }
      const amount = facts.amount ?? a.amount,
        term = facts.term ?? a.term;
      if (
        !Number.isFinite(amount) ||
        amount < 100000 ||
        amount > 5000000 ||
        !Number.isInteger(term) ||
        term < 3 ||
        term > 24
      )
        throw new Error('Проверьте сумму (100 000–5 000 000 ₽) и срок (3–24 мес.).');
      const offered = displayStatus(a) === 'OFFERED';
      if (
        (a.assistantMessageIds?.length || offered) &&
        (amount !== a.amount || term !== a.term || (facts.purpose && facts.purpose !== a.purpose))
      )
        this.snapshot(a, 'Условия подтверждены после диалога с помощником');
      a.amount = amount;
      a.term = term;
      a.purpose = facts.purpose ?? a.purpose;
      a.fields[`${a.product}_05`] = String(amount);
      a.fields[`${a.product}_06`] = String(term);
      a.fields[`${a.product}_04`] = a.purpose;
      a.assistantCaseId = facts.caseId;
      a.assistantMessageIds = [...(a.assistantMessageIds ?? []), facts.messageId];
      this.log(a, 'Клиент подтвердил сведения из диалога с помощником', 'Клиент');
      if (offered) {
        this.move(a, 'CHECKING', 'Изменённые условия отправлены на перепроверку', 'Клиент');
        a.stage = 1;
        a.nextAt = this.now() + 1600;
      }
    });
    return id;
  };
  private alternatives(a: Application) {
    return [
      this.offer(
        a,
        Math.round(a.amount * (2200000 / 3000000)),
        a.term,
        'Вариант А',
        'COUNTEROFFER',
      ),
      this.offer(a, a.amount, 24, 'Вариант Б', 'COUNTEROFFER'),
    ];
  }
  accept = async (id: string, offerId: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (
        ['ACCEPTED', 'SIGNED_DEMO', 'FUNDED_DEMO'].includes(displayStatus(a)) &&
        a.acceptedOffer?.id === offerId
      )
        return;
      const o = a.offers.find((o) => o.id === offerId);
      if (!o || o.revision !== a.revision || o.expires <= this.now())
        throw new Error('Предложение устарело. Отправьте условия на повторную проверку.');
      this.move(a, 'ACCEPTED', 'Предложение принято', 'Клиент');
      a.acceptedOffer = { ...o };
    });
  sign = async (id: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (['SIGNED_DEMO', 'FUNDED_DEMO'].includes(displayStatus(a))) return;
      if (!a.acceptedOffer) throw new Error('Сначала примите предложение.');
      this.move(a, 'SIGNED_DEMO', 'Договор подписан · имитация DEMO', 'Клиент');
    });
  fund = async (id: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) === 'FUNDED_DEMO') return;
      this.move(a, 'FUNDED_DEMO', 'Деньги на счёте · имитация DEMO');
    });
  cancel = async (id: string) =>
    this.transaction((s) => {
      const a = this.app(s, id);
      if (displayStatus(a) === 'CANCELLED') return;
      this.move(a, 'CANCELLED', 'Заявка отменена', 'Клиент');
      a.nextAt = undefined;
      a.offers = [];
    });
  reset = async () => {
    const s = seedState(this.now());
    this.storage.setItem(STORAGE_KEY, JSON.stringify(s));
    this.state = s;
    this.emit();
  };
  tick = async () => {
    if (!this.state.applications.some((a) => a.nextAt && a.nextAt <= this.now())) return;
    await this.transaction((s) => {
      for (const a of s.applications) {
        if (!a.nextAt || a.nextAt > this.now()) continue;
        if (displayStatus(a) === 'SUBMITTED') {
          this.move(a, 'CHECKING', 'Проверяем реквизиты и источники данных');
          a.stage = 1;
          a.nextAt = this.now() + 1600;
          continue;
        }
        if (displayStatus(a) !== 'CHECKING') {
          a.nextAt = undefined;
          continue;
        }
        if (a.scenario === 'external' && a.stage === 1 && !a.externalWait) {
          a.externalWait = true;
          a.reason = 'Ждём ответа источника: временный сбой БКИ';
          this.log(a, 'Источник временно недоступен. Ожидаем повторного ответа, это не отказ');
          a.nextAt = this.now() + 8000;
          continue;
        }
        if (a.stage < 4) {
          a.externalWait = false;
          if (a.reason.startsWith('Ждём ответа источника')) a.reason = '';
          a.stage += 1;
          this.log(
            a,
            [
              '',
              '',
              'Проверяем кредитную историю',
              'Оцениваем риск',
              'Проверяем платёжеспособность',
            ][a.stage],
          );
          a.nextAt = this.now() + 1600;
          continue;
        }
        a.nextAt = undefined;
        if (
          a.scenario === 'missing' &&
          !a.requests.some((r) => r.field === 'statement' && r.state === 'CLOSED')
        ) {
          a.requests.push({
            id: uid(),
            field: 'statement',
            text: 'Не хватает выписки за последние 3 месяца. Добавьте PDF или CSV.',
            state: 'OPEN',
            reason: 'Нужны данные о поступлениях за полный период',
            dueAt: this.now() + 3 * 86400000,
          });
          this.move(a, 'NEEDS_INFO', 'Запросили недостающую выписку');
        } else if (a.scenario === 'decline') {
          a.reason =
            'В демо-сценарии есть действующая просрочка более 90 дней. Подать новую заявку можно после погашения долга и обновления кредитной истории.';
          a.reasonCode = 'ACTIVE_OVERDUE_90';
          this.move(a, 'DECLINED', 'Демо-отказ: действующая просрочка более 90 дней');
        } else if (
          a.companyId === 'zerno' &&
          !a.checks?.authority &&
          coverage(a.flow, a.existing, a.amount, a.term) >= MIN_COVERAGE
        ) {
          a.reason = 'Нужно подтвердить полномочия представителя компании.';
          a.reasonCode = 'AUTHORITY_UNVERIFIED';
          this.move(a, 'MANUAL_REVIEW', 'Передано специалисту: ' + a.reason);
        } else if (coverage(a.flow, a.existing, a.amount, a.term) < MIN_COVERAGE) {
          a.reason = 'Платёжная нагрузка превышает допустимую: покрытие ниже 1,3×.';
          a.reasonCode = 'DSCR_BELOW_MIN';
          this.move(a, 'MANUAL_REVIEW', 'Передано специалисту: ' + a.reason);
        } else {
          a.offers = [this.offer(a, a.amount, a.term, 'Одобрено')];
          a.stage = 5;
          this.move(a, 'OFFERED', 'Подготовили предложение по демо-условиям');
        }
      }
    });
  };
}
