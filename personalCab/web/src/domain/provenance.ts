const sources: Record<string, string> = {
  BANK: 'Банк',
  FNS: 'ФНС',
  SME_REGISTER: 'Реестр МСП',
  BKI: 'БКИ',
  CLIENT: 'Клиент',
  CALCULATED: 'Расчёт',
  OTHER: 'Другое',
};
export function sourceLabel(source?: string | null) {
  if (!source?.trim()) return 'Источник не указан';
  return Object.hasOwn(sources, source) ? sources[source] : `Источник: ${source}`;
}
export function verificationLabel(status?: string | null) {
  switch (status) {
    case 'VERIFIED':
      return { label: 'Подтверждено', tone: 'verified' };
    case 'UNVERIFIED':
      return { label: 'Не проверено', tone: 'neutral' };
    case 'CONFLICT':
      return { label: 'Конфликт', tone: 'attention' };
    case 'EXPIRED':
      return { label: 'Устарело', tone: 'attention' };
    default:
      return {
        label: status?.trim() ? `Неизвестный статус (${status})` : 'Нет данных',
        tone: 'neutral',
      };
  }
}
export function fieldValue(value: unknown) {
  if (value == null || (typeof value === 'string' && !value.trim())) return 'Нет данных';
  return typeof value === 'object' ? JSON.stringify(value) : String(value);
}

/** Only actual company values; metadata is not inferred from the mapping. */
export function companyFieldValue(target: string, company?: Record<string, unknown>) {
  const keys = target
    .split(/\s*\+\s*/)
    .map((part) => /^companies\.([a-zA-Z0-9_]+)$/.exec(part)?.[1]);
  if (!keys.length || keys.some((key) => !key)) return undefined;
  const values = keys
    .map((key) => company?.[key!])
    .filter((value) => value != null && !(typeof value === 'string' && !value.trim()));
  return values.length ? values.map(fieldValue).join(' · ') : undefined;
}
