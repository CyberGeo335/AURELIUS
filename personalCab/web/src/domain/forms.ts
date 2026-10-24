import { fields, type FieldDefinition } from './fields';
import type { Application, Company, Product } from './types';
export function applicableFields(product: Product, entity: Company['entity']) {
  return fields.filter(
    (f) => f.product === product && (entity === 'IP' ? f.requiredIP : f.requiredOOO),
  );
}
export function defaultFields(company: Company, product: Product) {
  const ooo = company.entity === 'OOO';
  const values: Record<number, string> = {
    1: product,
    2: ooo ? 'ООО' : 'ИП',
    3: company.inn,
    4: 'Закупка товара',
    5: ooo ? '3000000' : '1500000',
    6: ooo ? '18' : '12',
    7: 'Без залога',
    8: 'Не участвует',
    9: company.registration,
    10: company.registration,
    11: '770101001',
    12: company.name,
    13: 'Карпов Илья Сергеевич',
    14: 'Общество с ограниченной ответственностью',
    15: company.registered,
    16: 'Действует',
    17: company.okved,
    18: ooo ? 'Оптовая торговля кофе' : 'Кофейная лавка «Зерно»',
    19: 'Москва, ул. Садовая, д. 12',
    20: 'Москва, ул. Садовая, д. 12',
    21: 'Москва',
    22: 'Микропредприятие',
    23: company.registered,
    24: ooo ? 'Белова Мария Андреевна' : 'Карпов Илья Сергеевич',
    25: ooo ? 'Бухгалтер' : 'Предприниматель',
    26: '+7 999 123-45-67',
    27: 'Карпов Илья Сергеевич',
    28: 'Генеральный директор',
    29: ooo ? 'Белова Мария Андреевна' : 'Карпов Илья Сергеевич',
    30: ooo ? 'Доверенность № 14 от 10.01.2026' : 'Лично, от своего имени',
    31: '',
    32: product === 'R02' ? '6' : '40702810900000012345',
    33: product === 'R02' ? '12' : 'Демо-банк',
    34: product === 'R02' ? 'Да' : '044525593',
  };
  return Object.fromEntries(
    applicableFields(product, company.entity).map((f) => [f.code, values[f.number] ?? '']),
  );
}
export function validateField(
  f: FieldDefinition,
  value: string,
  entity: Company['entity'],
): string | undefined {
  if (!value.trim()) return 'Заполните поле';
  const length =
    f.number === 3
      ? entity === 'IP'
        ? 12
        : 10
      : f.number === 9
        ? 13
        : f.number === 10
          ? 15
          : f.number === 11
            ? 9
            : f.product === 'R03' && f.number === 32
              ? 20
              : f.product === 'R03' && f.number === 34
                ? 9
                : 0;
  if (length && !new RegExp(`^\\d{${length}}$`).test(value)) return `Введите ${length} цифр`;
  if ([5, 6].includes(f.number) || (f.product === 'R02' && [32, 33].includes(f.number))) {
    const n = Number(value);
    if (!Number.isFinite(n) || n <= 0 || !Number.isInteger(n))
      return 'Введите положительное целое число';
    if (f.number === 5 && (n < 100000 || n > 5000000))
      return 'Демо-диапазон: от 100 000 до 5 000 000 ₽';
    if (f.number === 6 && (n < 3 || n > 24)) return 'Выберите от 3 до 24 месяцев';
  }
  if (f.number === 26 && !/^\+?[\d\s()-]{10,20}$/.test(value))
    return 'Введите телефон с кодом страны';
  if ([15, 23].includes(f.number) && !/^\d{4}-\d{2}-\d{2}$/.test(value))
    return 'Введите дату ГГГГ-ММ-ДД';
  return undefined;
}
export function validateApplication(a: Application, company: Company) {
  const errors: Record<string, string> = {};
  if (a.fields[`${a.product}_03`] !== company.inn)
    errors[`${a.product}_03`] = `В демо доступен ИНН выбранного профиля: ${company.inn}`;
  if (a.fields[`${a.product}_01`] !== a.product)
    errors[`${a.product}_01`] = 'Продукт должен совпадать с выбранной заявкой';
  if (a.fields[`${a.product}_02`] !== (company.entity === 'IP' ? 'ИП' : 'ООО'))
    errors[`${a.product}_02`] = 'Тип заявителя определяется выбранным профилем';
  for (const f of applicableFields(a.product, company.entity)) {
    const e = validateField(f, a.fields[f.code] ?? '', company.entity);
    if (e) errors[f.code] = e;
  }
  if (!a.businessConfirmed) errors.business = 'Подтвердите сведения о бизнесе';
  if (!a.statement) errors.statement = 'Добавьте выписку или внесите обороты';
  if (a.leasing === null) errors.leasing = 'Уточните регулярный платёж';
  if (!a.consentBki) errors.consentBki = 'Дайте отдельное согласие на запрос в БКИ';
  if (!a.consentData) errors.consentData = 'Подтвердите обработку данных';
  if (!Number.isFinite(a.flow) || a.flow <= 0)
    errors.flow = 'Укажите положительный свободный поток';
  if (!Number.isFinite(a.existing) || a.existing < 0)
    errors.existing = 'Укажите действующие платежи';
  return errors;
}
