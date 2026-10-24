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
export type Status = keyof typeof statusLabels;
export const backendStatus: Record<
  Status,
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
export const transitions: Record<Status, readonly Status[]> = {
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
export function assertTransition(from: Status, to: Status) {
  if (!transitions[from].includes(to))
    throw new Error('Состояние заявки изменилось. Обновите страницу и повторите действие.');
}
