import type { Application } from './types';

export const queueFilters = [
  ['all', 'Все'],
  ['checking', 'Проверяются'],
  ['decision', 'Ждут решения'],
  ['data', 'Нужны данные'],
  ['approved', 'Одобрено'],
  ['rejected', 'Отказ'],
  ['cancelled', 'Отменена'],
] as const;
export type QueueFilter = (typeof queueFilters)[number][0];
export const openRequests = (app: Application) =>
  (app.server?.requests ?? []).filter((r) => r.request_status === 'OPEN').length;
export const needsClientData = (app: Application) =>
  app.status === 'AWAITING_DATA' || openRequests(app) > 0;
export const awaitsDecision = (app: Application) =>
  app.status === 'UNDER_REVIEW' &&
  app.server?.assessment != null &&
  !app.server.offer_stale &&
  !openRequests(app);
export function queueMatches(app: Application, filter: QueueFilter) {
  switch (filter) {
    case 'decision':
      return awaitsDecision(app);
    case 'data':
      return needsClientData(app);
    case 'checking':
      return (
        ['SUBMITTED', 'UNDER_REVIEW'].includes(app.status) &&
        !awaitsDecision(app) &&
        !needsClientData(app)
      );
    case 'approved':
      return app.status === 'APPROVED';
    case 'rejected':
      return app.status === 'REJECTED';
    case 'cancelled':
      return app.status === 'CANCELLED';
    default:
      return true;
  }
}
export function lastQueueEvent(app: Application) {
  const dates = (app.server?.history ?? [])
    .map((e) => Date.parse(e.created_at))
    .filter(Number.isFinite);
  const result = dates.length ? Math.max(...dates) : Date.parse(app.server?.application_date ?? '');
  return Number.isFinite(result) ? result : undefined;
}
export function oldestFirst(a: Application, b: Application) {
  return (
    (lastQueueEvent(a) ?? Infinity) - (lastQueueEvent(b) ?? Infinity) ||
    a.id.localeCompare(b.id, undefined, { numeric: true })
  );
}
export function firstDecisionAverage(applications: readonly Application[]) {
  const durations = applications.flatMap((app) => {
    const events = app.server?.history ?? [];
    const submits = events
      .filter((e) => e.action === 'submit')
      .map((e) => Date.parse(e.created_at))
      .filter(Number.isFinite);
    if (!submits.length) return [];
    const start = Math.min(...submits);
    const reviews = events
      .filter((e) => e.action === 'review')
      .map((e) => Date.parse(e.created_at))
      .filter((at) => Number.isFinite(at) && at >= start);
    return reviews.length ? [Math.min(...reviews) - start] : [];
  });
  return durations.length ? durations.reduce((sum, n) => sum + n, 0) / durations.length : undefined;
}
export function durationLabel(ms?: number) {
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 60000) return 'Менее минуты';
  if (ms < 3600000) return `${Math.floor(ms / 60000)} мин`;
  if (ms < 86400000) return `${Math.floor(ms / 3600000)} ч`;
  return `${Math.floor(ms / 86400000)} дн`;
}
