import type { Application, Company, ServerRequirement, Product } from './types';
export function initialFields(rows: ServerRequirement[], app: Application, company: Company) {
  const values = { ...app.fields };
  for (const r of rows) {
    if (values[r.field_code] !== undefined) continue;
    let value: unknown;
    if (r.field_number === 1) value = app.product;
    else if (r.field_number === 2)
      value = company.server?.entity_type === 'INDIVIDUAL_ENTREPRENEUR' ? 'ИП' : 'Юридическое лицо';
    else if (r.field_number === 4) value = app.purpose;
    else if (r.field_number === 5) value = app.server?.requested_amount;
    else if (r.field_number === 6) value = app.server?.requested_term_months;
    else if (r.field_number !== 31) {
      const parts = r.target_db_field
        .split(/\s*\+\s*/)
        .map((part) => {
          const [table, key] = part.split('.');
          const source =
            table === 'companies'
              ? company.server
              : table === 'application_details'
                ? app.server?.details
                : table === 'application_product_details'
                  ? app.server?.product_details
                  : undefined;
          return source?.[key];
        })
        .filter((v) => v !== undefined && v !== null);
      value = parts.length ? parts.join(' · ') : undefined;
    }
    values[r.field_code] = value === undefined || value === null ? '' : String(value);
  }
  return values;
}

export const formStepTitles = [
  'Запрос и условия',
  'Реквизиты бизнеса',
  'Контакты и подписант',
  'Подтверждение и согласия',
  'Проверка и отправка',
];
export const consentLabels = [
  ['businessConfirmed', 'Подтверждаю сведения о бизнесе'],
  ['consentData', 'Согласен на обработку данных'],
  ['consentBki', 'Согласен на запрос кредитной истории'],
] as const;
export type FormConsents = Record<(typeof consentLabels)[number][0], boolean>;
export function fieldStep(row: ServerRequirement, product: Product) {
  const n = row.field_number;
  if (n === 31) return 3;
  if ([1, 4, 5, 6, 7, 8].includes(n) || (product === 'R02' && n >= 32)) return 0;
  if (n >= 24 && n <= 30) return 2;
  return 1;
}
export function formMissing(
  rows: readonly ServerRequirement[],
  product: Product,
  values: Record<string, string>,
  consents: FormConsents,
  tranche: string,
  unit: string,
) {
  const missing = rows
    .filter((row) =>
      row.field_number === 31
        ? values[row.field_code] !== 'Подтверждаю'
        : !values[row.field_code]?.trim(),
    )
    .map((row) => ({ key: row.field_code, label: row.field_label, step: fieldStep(row, product) }));
  for (const [key, label] of consentLabels)
    if (!consents[key]) missing.push({ key, label, step: 3 });
  if (product !== 'R01') {
    if (!tranche.trim() || !Number.isInteger(Number(tranche)) || Number(tranche) < 1)
      missing.push({ key: 'tranche', label: 'Срок транша', step: 0 });
    if (!['DAYS', 'MONTHS'].includes(unit))
      missing.push({ key: 'unit', label: 'Единица срока транша', step: 0 });
  }
  return missing;
}
export function restoredFormStep(step: number, missing: readonly { step: number }[]) {
  const saved = Number.isInteger(step) && step >= 0 && step < formStepTitles.length ? step : 0;
  return Math.min(saved, ...missing.map((item) => item.step));
}
