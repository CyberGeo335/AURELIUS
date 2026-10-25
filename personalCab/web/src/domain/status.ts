export const statusLabels = {
  DRAFT: 'Черновик',
  SUBMITTED: 'Отправлена',
  CHECKING: 'Проверяем',
  NEEDS_INFO: 'Нужны данные',
  MANUAL_REVIEW: 'Проверяет специалист',
  OFFERED: 'Одобрено',
  ACCEPTED: 'Предложение принято',
  SIGNED_DEMO: 'Подписано · демо',
  FUNDED_DEMO: 'Деньги на счёте · демо',
  DECLINED: 'Отказ',
  CANCELLED: 'Отменена',
} as const;
export type UiStatus = keyof typeof statusLabels;
export type Status =
  'DRAFT' | 'SUBMITTED' | 'UNDER_REVIEW' | 'AWAITING_DATA' | 'APPROVED' | 'REJECTED' | 'CANCELLED';
export const backendStatus: Record<
  UiStatus,
  { application: string; dialogue?: string; decision?: string; offer?: string }
> = {
  DRAFT: { application: 'DRAFT', dialogue: 'DISCOVERY / NEEDS_INPUT' },
  SUBMITTED: { application: 'SUBMITTED', dialogue: 'REQUEST_READY' },
  CHECKING: { application: 'UNDER_REVIEW', dialogue: 'WAITING_EXTERNAL' },
  NEEDS_INFO: { application: 'AWAITING_DATA', dialogue: 'WAITING_DOCUMENTS / WAITING_CONSENT' },
  MANUAL_REVIEW: { application: 'UNDER_REVIEW', decision: 'MANUAL_REVIEW' },
  OFFERED: { application: 'APPROVED', offer: 'PROPOSED' },
  ACCEPTED: { application: 'APPROVED', offer: 'ACCEPTED' },
  SIGNED_DEMO: { application: 'APPROVED', offer: 'ACCEPTED' },
  FUNDED_DEMO: { application: 'APPROVED', offer: 'ACCEPTED' },
  DECLINED: { application: 'REJECTED', decision: 'REJECT' },
  CANCELLED: { application: 'CANCELLED', dialogue: 'CANCELLED' },
};
export const transitions: Record<UiStatus, readonly UiStatus[]> = {
  DRAFT: ['SUBMITTED', 'CANCELLED'],
  SUBMITTED: ['CHECKING', 'CANCELLED'],
  CHECKING: ['CHECKING', 'NEEDS_INFO', 'MANUAL_REVIEW', 'OFFERED', 'DECLINED', 'CANCELLED'],
  NEEDS_INFO: ['CHECKING', 'CANCELLED'],
  MANUAL_REVIEW: ['OFFERED', 'NEEDS_INFO', 'DECLINED', 'CANCELLED'],
  OFFERED: ['CHECKING', 'ACCEPTED', 'CANCELLED'],
  ACCEPTED: ['SIGNED_DEMO'],
  SIGNED_DEMO: ['FUNDED_DEMO'],
  FUNDED_DEMO: [],
  DECLINED: [],
  CANCELLED: [],
};
export function assertTransition(from: UiStatus, to: UiStatus) {
  if (!transitions[from].includes(to))
    throw new Error('Состояние заявки изменилось. Обновите страницу и повторите действие.');
}

// UI labels are derived from the DB lifecycle plus decision/offer status.
import type { Application } from './types';
export function displayStatus(a: Application): UiStatus {
  if (a.demoExecution) return a.demoExecution;
  if (a.status === 'UNDER_REVIEW')
    return a.decision === 'MANUAL_REVIEW' ? 'MANUAL_REVIEW' : 'CHECKING';
  if (a.status === 'AWAITING_DATA') return 'NEEDS_INFO';
  if (a.status === 'APPROVED') return a.offerStatus === 'ACCEPTED' ? 'ACCEPTED' : 'OFFERED';
  if (a.status === 'REJECTED') return 'DECLINED';
  return a.status;
}
// Used by mock scenarios only. HTTP adapters never synthesize DB transitions.
export function setMockStatus(a: Application, status: UiStatus) {
  const mapped = backendStatus[status];
  a.status = mapped.application as Status;
  a.decision = mapped.decision as Application['decision'];
  a.offerStatus = mapped.offer as Application['offerStatus'];
  a.demoExecution = status === 'SIGNED_DEMO' || status === 'FUNDED_DEMO' ? status : undefined;
}
