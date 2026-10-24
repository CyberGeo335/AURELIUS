export const statementPeriods = Array.from(
  { length: 12 },
  (_, i) => `${i < 3 ? 2025 : 2026}-${String(((i + 9) % 12) + 1).padStart(2, '0')}`,
);
export function parseStatement(text: string) {
  const rows = text
    .replace(/^\uFEFF/, '')
    .trim()
    .split(/\r?\n/);
  const delimiter = rows[0]?.includes(';') ? ';' : ',';
  const headers =
    rows
      .shift()
      ?.split(delimiter)
      .map((s) => s.trim().toLowerCase()) ?? [];
  const monthIndex = headers.indexOf('month'),
    amountIndex = headers.indexOf('incoming_rub');
  if (monthIndex < 0 || amountIndex < 0)
    throw new Error('В CSV нужны столбцы month (ГГГГ-ММ) и incoming_rub (поступления в рублях).');
  const data: Record<string, number> = {};
  for (const row of rows) {
    if (!row.trim()) continue;
    const cells = row.split(delimiter);
    const period = cells[monthIndex]?.trim();
    const rawAmount = cells[amountIndex]?.trim();
    const amount = rawAmount ? Number(rawAmount) : NaN;
    if (!statementPeriods.includes(period) || !Number.isFinite(amount) || amount < 0)
      throw new Error(
        'Проверьте месяц и сумму поступлений в CSV. Период: октябрь 2025 — сентябрь 2026.',
      );
    if (period in data)
      throw new Error(`Месяц ${period} повторяется. Оставьте одну строку с итогом.`);
    data[period] = amount;
  }
  if (!Object.keys(data).length) throw new Error('В выписке нет строк с поступлениями.');
  return data;
}
