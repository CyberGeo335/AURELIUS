import { describe, it, expect, afterEach } from 'vitest';
import { MockCreditApi, STORAGE_KEY } from '../mocks/MockCreditApi';
import type { Application, Scenario } from '../domain/types';
let now = Date.UTC(2026, 9, 24, 10);
const apis: MockCreditApi[] = [];
function api() {
  const a = new MockCreditApi(localStorage, () => now);
  apis.push(a);
  return a;
}
afterEach(() => {
  apis.forEach((a) => a.destroy());
  apis.length = 0;
  now = Date.UTC(2026, 9, 24, 10);
});
async function completeDraft(
  a: MockCreditApi,
  scenario: Scenario = 'normal',
  profile: 'karpov' | 'zerno' = 'karpov',
) {
  const id = await a.createDraft(profile, 'R01');
  const draft = a.getSnapshot().applications.find((a) => a.id === id)!;
  await a.saveDraft(id, {
    businessConfirmed: true,
    statement: true,
    leasing: true,
    consentBki: true,
    consentData: true,
    scenario,
    fields: { ...draft.fields, R01_31: 'Подтверждаю' },
  });
  return id;
}
async function process(a: MockCreditApi) {
  for (let i = 0; i < 7; i++) {
    now += 2000;
    await a.tick();
  }
}
const find = (a: MockCreditApi, id: string): Application =>
  a.getSnapshot().applications.find((a) => a.id === id)!;
describe('Mock credit lifecycle', () => {
  it('submits, approves, accepts, signs and funds without duplicates', async () => {
    const a = api();
    const id = await completeDraft(a);
    await a.submit(id);
    await a.submit(id);
    expect(find(a, id).history.filter((e) => e.text.startsWith('Заявка отправлена'))).toHaveLength(
      1,
    );
    await process(a);
    const offer = find(a, id).offers[0];
    expect(find(a, id).status).toBe('APPROVED');
    await a.accept(id, offer.id);
    await a.accept(id, offer.id);
    await a.sign(id);
    await a.sign(id);
    await a.fund(id);
    await a.fund(id);
    expect(find(a, id).status).toBe('APPROVED');
    expect(find(a, id).history.filter((e) => e.text.includes('Договор подписан'))).toHaveLength(1);
    expect(find(api(), id).status).toBe('APPROVED');
  });
  it('blocks incomplete drafts and preserves missing-data history', async () => {
    const a = api();
    const empty = await a.createDraft('karpov', 'R02');
    await expect(a.submit(empty)).rejects.toThrow();
    const id = await completeDraft(a, 'missing');
    await a.submit(id);
    await process(a);
    expect(find(a, id).status).toBe('AWAITING_DATA');
    const request = find(a, id).requests[0];
    await expect(a.answerRequest(id, request.id, 'Ответ')).rejects.toThrow();
    await a.answerRequest(id, request.id, 'Выписка приложена', 'statement.pdf');
    await a.answerRequest(id, request.id, 'Выписка приложена', 'statement.pdf');
    expect(find(a, id).revision).toBe(2);
    await process(a);
    expect(find(a, id).status).toBe('APPROVED');
    expect(find(a, id).revisions).toHaveLength(1);
    expect(find(a, id).requests[0].state).toBe('CLOSED');
  });
  it('routes insufficient coverage to review and synchronizes decisions', async () => {
    const a = api();
    const id = await completeDraft(a, 'normal', 'zerno');
    await a.submit(id);
    await process(a);
    expect(find(a, id).status).toBe('UNDER_REVIEW');
    await expect(a.bankDecision(id, 1, 'A', 'коротко')).rejects.toThrow();
    await expect(
      a.bankDecision(id, 1, 'BOTH', 'Проверки ещё не завершены сотрудником'),
    ).rejects.toThrow('обязательные проверки');
    await a.resolveData(id, 'authority', 'Полномочия подтверждены по документу');
    await a.resolveData(id, 'revenue', 'Расхождение подтверждено по источнику');
    await a.bankDecision(
      id,
      1,
      'BOTH',
      'Расхождение объяснимо, варианты покрываются свободным потоком.',
    );
    const b = api();
    expect(find(b, id).offers).toHaveLength(2);
    await expect(a.bankDecision(id, 1, 'A', 'Повторное решение сотрудника')).rejects.toThrow();
  });
  it('invalidates old offers on revision and on expiry', async () => {
    const a = api();
    const id = await completeDraft(a);
    await a.submit(id);
    await process(a);
    const old = find(a, id).offers[0];
    await a.revise(id, 1500000, 18);
    await expect(a.accept(id, old.id)).rejects.toThrow();
    await process(a);
    const fresh = find(a, id).offers[0];
    now = fresh.expires + 1;
    await expect(a.accept(id, fresh.id)).rejects.toThrow();
  });
  it('waits for an external source instead of declining', async () => {
    const a = api();
    const id = await completeDraft(a, 'external');
    await a.submit(id);
    now += 2000;
    await a.tick();
    now += 2000;
    await a.tick();
    expect(find(a, id).externalWait).toBe(true);
    expect(find(a, id).status).toBe('UNDER_REVIEW');
    now += 9000;
    await process(a);
    expect(find(a, id).status).toBe('APPROVED');
  });
  it('provides understandable decline and rejects illegal signing', async () => {
    const a = api();
    const id = await completeDraft(a, 'decline');
    await a.submit(id);
    await process(a);
    expect(find(a, id).reasonCode).toBe('ACTIVE_OVERDUE_90');
    expect(find(a, id).reason).toContain('погашения');
    await expect(a.sign(id)).rejects.toThrow();
  });
  it('receives storage events and resets both clients', async () => {
    const a = api(),
      b = api();
    await a.createDraft('karpov', 'R01');
    window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY }));
    expect(b.getSnapshot().applications).toHaveLength(7);
    await a.reset();
    window.dispatchEvent(new StorageEvent('storage', { key: STORAGE_KEY }));
    expect(b.getSnapshot().applications).toHaveLength(7);
  });
  it('keeps confirmed assistant facts in the same draft and preserves explicit consent', async () => {
    const a = api();
    const existing = await a.createDraft('karpov', 'R02');
    const facts = {
      messageId: 'reply-1',
      caseId: 'case-1',
      amount: 2200000,
      term: 18,
      purpose: 'Закупки каждый месяц',
    };
    const id = await a.applyAssistant('karpov', 'R02', facts);
    expect(id).toBe(existing);
    expect(find(a, id).consentBki).toBe(false);
    expect(find(a, id).amount).toBe(2200000);
    await a.applyAssistant('karpov', 'R02', facts);
    expect(find(a, id).revision).toBe(1);
    await a.applyAssistant('karpov', 'R02', {
      ...facts,
      messageId: 'reply-1-edited',
      applicationId: id,
      amount: 1800000,
    });
    expect(find(a, id).revision).toBe(2);
    expect(find(a, id).revisions[0].amount).toBe(2200000);
    expect(a.getSnapshot().applications.filter((app) => app.id === id)).toHaveLength(1);
    await expect(a.applyAssistant('zerno', 'R02', { ...facts, applicationId: id })).rejects.toThrow(
      'Нет доступа',
    );
    expect(find(api(), id).amount).toBe(1800000);
  });
  it('blocks incomplete CSV coverage and remembers the furthest visited step', async () => {
    const a = api();
    const id = await completeDraft(a);
    await a.saveDraft(id, { step: 3, statementMonths: ['2025-10'], monthly: Array(12).fill(1) });
    await a.saveDraft(id, { step: 0 });
    expect(find(a, id).furthestStep).toBe(3);
    await expect(a.submit(id)).rejects.toThrow('Не хватает 11 месяцев');
  });
  it('validates request deadlines and preserves field, reason and answer revision', async () => {
    const a = api();
    const id = 'R01-2026-00151';
    const revision = find(a, id).revision;
    await expect(
      a.bankDecision(id, revision, 'INFO', 'Добавьте доверенность подписанта'),
    ).rejects.toThrow('срок');
    await a.bankDecision(id, revision, 'INFO', 'Добавьте доверенность подписанта', {
      field: 'authority',
      dueAt: now + 86400000,
    });
    const request = find(a, id).requests.at(-1)!;
    expect(request.field).toBe('authority');
    expect(request.dueAt).toBe(now + 86400000);
    await a.answerRequest(id, request.id, 'Доверенность приложена', 'authority.pdf');
    expect(find(a, id).revision).toBe(revision + 1);
    expect(find(a, id).status).toBe('UNDER_REVIEW');
  });
});
