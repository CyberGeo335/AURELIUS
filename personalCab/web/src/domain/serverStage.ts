import type { ServerApplication } from './types';

export type TrackRole = 'client' | 'bank';
export type StageState = 'done' | 'current' | 'unknown';
export interface ServerTrack {
  states: StageState[];
  current: number | null;
  stopped: boolean;
  notice: string | null;
}

function filled(value: unknown): boolean {
  if (value === null || value === undefined) return false;
  if (typeof value === 'string') return value.trim().length > 0;
  if (Array.isArray(value)) return value.length > 0;
  if (typeof value === 'object') return Object.keys(value).length > 0;
  return typeof value !== 'number' || Number.isFinite(value);
}

/** Each step needs its own evidence. Later steps never complete earlier ones.
 * requiredFields is the applicable, authoritative requirement list from /state;
 * without it an empty/incomplete field set cannot establish completeness.
 */
export function stageFromServer(
  a: ServerApplication,
  role: TrackRole,
  requiredFields?: readonly string[],
): ServerTrack | null {
  if (a.application_status === 'DRAFT' || a.application_status === 'CANCELLED') return null;
  const bank = role === 'bank';
  const states: StageState[] = Array(bank ? 6 : 5).fill('unknown');
  const last = states.length - 1;
  const result: ServerTrack = { states, current: null, stopped: false, notice: null };
  const current = (index: number) => {
    states[index] = 'current';
    result.current = index;
  };
  if (a.offer_stale) {
    result.notice = 'Требуется повторная проверка';
    return result;
  }
  if (a.application_status === 'REJECTED') {
    current(last);
    result.notice = 'Решение: отказ';
    return result;
  }

  const submitted =
    a.history.some((event) => event.action === 'submit') ||
    ['SUBMITTED', 'UNDER_REVIEW', 'AWAITING_DATA', 'APPROVED'].includes(a.application_status);
  const openRequest = a.requests.some((request) => request.request_status === 'OPEN');
  const verified = (code: string) =>
    a.fields.some(
      (field) =>
        field.field_code === code &&
        filled(field.field_value) &&
        field.verification_status === 'VERIFIED',
    );
  const allFieldsVerified = a.fields.every(
    (field) => field.verification_status === 'VERIFIED' && filled(field.field_value),
  );
  const dataConfirmed =
    !!requiredFields?.length && requiredFields.every(verified) && allFieldsVerified && !openRequest;

  if (submitted) states[0] = 'done';
  if (dataConfirmed) states[1] = 'done';

  // Events submit/score/revise are written BEFORE guarded_score. Neither such
  // an event nor MANUAL_REVIEW proves that prediction succeeded. A client is
  // deliberately not sent assessment; never infer its score from a bank decision.
  const pd = a.assessment?.risk_assessment?.pd_application_1y;
  const scored = bank && typeof pd === 'number' && Number.isFinite(pd) && pd >= 0 && pd <= 1;
  if (scored) states[3] = 'done';
  if (bank && scored && a.assessment?.policy_version && a.decision) states[4] = 'done';

  // A review event can mean REQUEST_DATA; an unpublished DRAFT offer is not
  // the employee's final decision. No historical event completes a later revision.
  const decided = a.application_status === 'APPROVED';
  if (decided) current(last);
  else if (
    a.application_status === 'AWAITING_DATA' ||
    openRequest ||
    a.decision === 'REQUEST_DATA'
  ) {
    current(1);
  } else if (bank && a.decision === 'MANUAL_REVIEW') {
    current(last);
    result.stopped = true;
  } else if (a.application_status === 'SUBMITTED') current(0);
  // No evidence identifies the current internal phase of a generic UNDER_REVIEW.
  return result;
}
