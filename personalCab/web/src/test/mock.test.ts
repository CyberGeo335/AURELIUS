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
    expect(find(a, id).status).toBe('OFFERED');
    await a.accept(id, offer.id);
    await a.accept(id, offer.id);
    await a.sign(id);
    await a.sign(id);
    await a.fund(id);
    await a.fund(id);
    expect(find(a, id).status).toBe('FUNDED_DEMO');
    expect(find(a, id).history.filter((e) => e.text.includes('Договор подписан'))).toHaveLength(1);
    expect(find(api(), id).status).toBe('FUNDED_DEMO');
  });
  it('blocks incomplete drafts and preserves missing-data history', async () => {
    const a = api();
    const empty = await a.createDraft('karpov', 'R02');
    await expect(a.submit(empty)).rejects.toThrow();
    const id = await completeDraft(a, 'missing');
    await a.submit(id);
    await process(a);
    expect(find(a, id).status).toBe('NEEDS_INFO');
    const request = find(a, id).requests[0];
    await expect(a.answerRequest(id, request.id, 'Ответ')).rejects.toThrow();
    await a.answerRequest(id, request.id, 'Выписка приложена', 'statement.pdf');
    await a.answerRequest(id, request.id, 'Выписка приложена', 'statement.pdf');
    expect(find(a, id).revision).toBe(2);
    await process(a);
    expect(find(a, id).status).toBe('OFFERED');
    expect(find(a, id).revisions).toHaveLength(1);
    expect(find(a, id).requests[0].state).toBe('CLOSED');
  });
  it('routes insufficient coverage to review and synchronizes decisions', async () => {
    const a = api();
    const id = await completeDraft(a, 'normal', 'zerno');
    await a.submit(id);
    await process(a);
    expect(find(a, id).status).toBe('MANUAL_REVIEW');
    await expect(a.bankDecision(id, 1, 'A', 'коротко')).rejects.toThrow();
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
    expect(find(a, id).status).toBe('CHECKING');
    now += 9000;
    await process(a);
    expect(find(a, id).status).toBe('OFFERED');
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
    expect(b.getSnapshot().applications).toHaveLength(6);
  });
});
