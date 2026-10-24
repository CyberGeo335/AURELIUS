export const ANNUAL_RATE = 24.9;
export const MIN_COVERAGE = 1.3;
export function payment(amount: number, months: number, annualRate = ANNUAL_RATE) {
  if (
    !Number.isFinite(amount) ||
    amount <= 0 ||
    !Number.isInteger(months) ||
    months <= 0 ||
    !Number.isFinite(annualRate) ||
    annualRate < 0
  )
    throw new Error('Проверьте сумму, срок и ставку.');
  const rate = annualRate / 1200;
  return rate === 0 ? amount / months : (amount * rate) / (1 - Math.pow(1 + rate, -months));
}
export const coverage = (flow: number, existing: number, amount: number, months: number) =>
  flow / (existing + payment(amount, months));
export const money = (value: number) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(value) + ' ₽';
export const decimal = (value: number, digits = 2) =>
  new Intl.NumberFormat('ru-RU', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
export const date = (value: number) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: 'numeric',
    month: 'long',
    timeZone: 'Europe/Moscow',
  }).format(value);
export const datetime = (value: number) =>
  new Intl.DateTimeFormat('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    timeZone: 'Europe/Moscow',
  }).format(value);
export function schedule(amount: number, months: number, start = Date.now()) {
  const monthly = payment(amount, months);
  let balance = amount;
  const base = new Date(start);
  return Array.from({ length: months }, (_, i) => {
    const interest = (balance * ANNUAL_RATE) / 1200;
    const principal = Math.min(balance, monthly - interest);
    balance = Math.max(0, balance - principal);
    return {
      date: Date.UTC(base.getUTCFullYear(), base.getUTCMonth() + i + 1, 25, 9),
      payment: principal + interest,
      interest,
      principal,
      balance,
    };
  });
}
