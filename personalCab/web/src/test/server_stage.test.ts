import { describe, expect, it } from 'vitest';
import { stageFromServer, type TrackRole } from '../domain/serverStage';
import type { ServerApplication } from '../domain/types';
import type { Status } from '../domain/status';

function serverApplication(patch: Partial<ServerApplication> = {}): ServerApplication {
  return {
    application_id: 456,
    company_id: 123,
    product_code: 'R01',
    requested_amount: '3000000',
    requested_term_months: 36,
    purpose: 'Оборотные средства',
    application_status: 'UNDER_REVIEW',
    application_date: '2026-10-26T09:00:00Z',
    version: 1,
    decision: undefined,
    offer: null,
    assessment: null,
    fields: [],
    requests: [],
    history: [],
    reasons: [],
    details: null,
    product_details: null,
    form_state: {},
    ...patch,
  };
}
const required = ['R01_03', 'R01_05'];
const fields = required.map((field_code) => ({
  field_code,
  field_value: '123',
  verification_status: 'VERIFIED',
  value_source: 'BANK',
}));
const event = (action: string) => ({ action, event_id: 1, created_at: '2026-10-26T09:00:00Z' });
const scored = {
  risk_assessment: { pd_application_1y: 0.13, pd_limit_1y: 0.2 },
  policy_version: 'DEMO_ANNUAL_PD_V2',
};
const roles: TrackRole[] = ['client', 'bank'];

describe.each(roles)('%s server stage evidence', (role) => {
  it.each(['DRAFT', 'CANCELLED'] as const)(
    'hides %s even with historical events and results',
    (application_status) => {
      expect(
        stageFromServer(
          serverApplication({
            application_status,
            assessment: scored,
            decision: 'APPROVE',
            history: [event('submit'), event('review')],
          }),
          role,
          required,
        ),
      ).toBeNull();
    },
  );
  it('shows rejection without a completed prefix', () => {
    const track = stageFromServer(
      serverApplication({
        application_status: 'REJECTED',
        decision: 'REJECT',
        assessment: scored,
        fields,
        history: [event('submit'), event('review')],
      }),
      role,
      required,
    )!;
    expect(track.states.at(-1)).toBe('current');
    expect(track.states.slice(0, -1).every((state) => state === 'unknown')).toBe(true);
    expect(track.notice).toBe('Решение: отказ');
  });
  it('neutralizes an outdated offer despite previous successful checks', () => {
    const track = stageFromServer(
      serverApplication({
        offer_stale: { reason: 'Changed source' },
        assessment: scored,
        fields,
        decision: 'MANUAL_REVIEW',
        history: [event('submit'), event('score'), event('review')],
      }),
      role,
      required,
    )!;
    expect(track.states.every((state) => state === 'unknown')).toBe(true);
    expect(track.current).toBeNull();
    expect(track.stopped).toBe(false);
    expect(track.notice).toBe('Требуется повторная проверка');
  });
  it('shows a submitted application at reception', () => {
    const track = stageFromServer(
      serverApplication({ application_status: 'SUBMITTED' }),
      role,
      required,
    )!;
    expect(track.current).toBe(0);
    expect(track.states.slice(1).every((s) => s === 'unknown')).toBe(true);
  });
  it('does not guess the internal phase of UNDER_REVIEW', () => {
    const track = stageFromServer(serverApplication(), role, required)!;
    expect(track.current).toBeNull();
    expect(track.states[0]).toBe('done');
    expect(track.states.slice(1).every((s) => s === 'unknown')).toBe(true);
  });
  it('requires the complete authoritative field list and VERIFIED values', () => {
    expect(stageFromServer(serverApplication({ fields }), role, required)!.states[1]).toBe('done');
    for (const requiredFields of [undefined, [], [...required, 'R01_06']])
      expect(stageFromServer(serverApplication({ fields }), role, requiredFields)!.states[1]).toBe(
        'unknown',
      );
    expect(
      stageFromServer(serverApplication({ fields: fields.slice(0, 1) }), role, required)!.states[1],
    ).toBe('unknown');
  });
  it.each(['UNVERIFIED', 'CONFLICT', 'EXPIRED'])(
    'does not complete data verification with %s fields',
    (verification_status) => {
      expect(
        stageFromServer(
          serverApplication({ fields: fields.map((f) => ({ ...f, verification_status })) }),
          role,
          required,
        )!.states[1],
      ).toBe('unknown');
    },
  );
  it.each([null, '', '   ', [], {}, undefined])(
    'does not treat empty value %j as completed',
    (field_value) => {
      expect(
        stageFromServer(
          serverApplication({ fields: fields.map((f) => ({ ...f, field_value })) }),
          role,
          required,
        )!.states[1],
      ).toBe('unknown');
    },
  );
  it.each([0, false])(
    'accepts filled verified value %j without truthiness coercion',
    (field_value) => {
      expect(
        stageFromServer(
          serverApplication({ fields: fields.map((f) => ({ ...f, field_value })) }),
          role,
          required,
        )!.states[1],
      ).toBe('done');
    },
  );
  it.each(['OPEN', 'ANSWERED', 'CANCELLED'])('handles %s data requests', (request_status) => {
    const track = stageFromServer(
      serverApplication({
        fields,
        requests: [
          {
            request_id: 1,
            field_code: 'R01_03',
            question_text: 'Уточните',
            request_status,
            answer_value: null,
          },
        ],
      }),
      role,
      required,
    )!;
    expect(track.states[1]).toBe(request_status === 'OPEN' ? 'current' : 'done');
  });
  it('treats verify events and closed requests as evidence of actions, not full field verification', () => {
    const track = stageFromServer(
      serverApplication({
        history: [event('verify'), event('answer')],
        verifications: [
          {
            details: { kind: 'revenue', source_ref: 'source', comment: 'reviewed' },
            created_at: '2026-10-26',
            first_name: 'Иван',
            last_name: 'Иванов',
          },
        ],
      }),
      role,
      required,
    )!;
    expect(track.states[1]).toBe('unknown');
  });
  it.each(['submit', 'score', 'revise', 'review'])(
    'does not infer prediction from %s event',
    (action) => {
      const track = stageFromServer(
        serverApplication({
          history: [event(action)],
          decision: 'MANUAL_REVIEW',
          assessment: { policy_version: 'DEMO_ANNUAL_PD_V2' },
          reasons: [{ code: 'DB_INPUTS_UNAVAILABLE', message: 'Missing inputs' }],
        }),
        role,
        required,
      )!;
      expect(track.states[3]).toBe('unknown');
      if (role === 'bank') expect(track.states[4]).toBe('unknown');
    },
  );
  it('only marks prediction and policy as completed for the employee with actual evidence', () => {
    const track = stageFromServer(
      serverApplication({ assessment: scored, decision: 'MANUAL_REVIEW' }),
      role,
      required,
    )!;
    expect(track.states[3]).toBe(role === 'bank' ? 'done' : 'unknown');
    if (role === 'bank') {
      expect(track.states[4]).toBe('done');
      expect(track.stopped).toBe(true);
      expect(track.current).toBe(5);
    }
    expect(track.states[2]).toBe('unknown');
  });
  it.each([null, undefined, NaN, Infinity, -0.1, 1.1])(
    'rejects missing/invalid PD %j as completion evidence',
    (pd_application_1y) => {
      expect(
        stageFromServer(
          serverApplication({ assessment: { risk_assessment: { pd_application_1y } } }),
          role,
          required,
        )!.states[3],
      ).toBe('unknown');
    },
  );
  it('does not confuse REQUEST_DATA with the final decision', () => {
    const track = stageFromServer(
      serverApplication({
        application_status: 'AWAITING_DATA',
        decision: 'REQUEST_DATA',
        history: [event('review')],
      }),
      role,
      required,
    )!;
    expect(track.current).toBe(1);
    expect(track.states.at(-1)).toBe('unknown');
  });
  it('shows approval without completing unsupported predecessor steps', () => {
    const track = stageFromServer(
      serverApplication({ application_status: 'APPROVED', decision: 'APPROVE' }),
      role,
      required,
    )!;
    expect(track.current).toBe(track.states.length - 1);
    expect(track.states[1]).toBe('unknown');
    expect(track.states[2]).toBe('unknown');
    expect(track.states[3]).toBe('unknown');
    expect(track.stopped).toBe(false);
  });
});

it('covers status/decision/assessment/offer/history combinations without completing unsupported phases', () => {
  const statuses: Status[] = [
    'DRAFT',
    'SUBMITTED',
    'UNDER_REVIEW',
    'AWAITING_DATA',
    'APPROVED',
    'REJECTED',
    'CANCELLED',
  ];
  const decisions: ServerApplication['decision'][] = [
    undefined,
    'APPROVE',
    'REJECT',
    'REQUEST_DATA',
    'MANUAL_REVIEW',
  ];
  const offers: ServerApplication['offer'][] = [
    null,
    ...(['DRAFT', 'PROPOSED', 'ACCEPTED', 'DECLINED'] as const).map((offer_status) => ({
      offer_id: 1,
      offer_status,
      offered_amount: '3000000',
      offered_term_months: 36,
      offered_annual_rate_pct: '28',
    })),
  ];
  for (const role of roles)
    for (const application_status of statuses)
      for (const decision of decisions)
        for (const assessment of [null, { policy_version: 'demo' }, scored])
          for (const offer of offers)
            for (const history of [[], [event('submit')], [event('score')], [event('review')]]) {
              const track = stageFromServer(
                serverApplication({ application_status, decision, assessment, offer, history }),
                role,
                required,
              );
              if (['DRAFT', 'CANCELLED'].includes(application_status)) {
                expect(track).toBeNull();
                continue;
              }
              expect(track!.states[2]).toBe('unknown');
              if (role === 'client') expect(track!.states[3]).toBe('unknown');
              expect(track!.states.filter((s) => s === 'current').length).toBe(
                track!.current === null ? 0 : 1,
              );
            }
});

it('recognizes a calculated zero PD and does not invent a policy version', () => {
  const a = serverApplication({
    assessment: { risk_assessment: { pd_application_1y: 0 } },
    decision: 'MANUAL_REVIEW',
  });
  const track = stageFromServer(a, 'bank', required)!;
  expect(track.states[3]).toBe('done');
  expect(track.states[4]).toBe('unknown');
});
