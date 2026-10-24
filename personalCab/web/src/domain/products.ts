import type { Product } from './types';
export type Need = 'once' | 'recurring' | 'gap';
export const productInfo: Record<
  Product,
  {
    description: string;
    reason: string;
    min: number;
    max: number;
    minTerm: number;
    maxTerm: number;
  }
> = {
  R01: {
    description: 'Деньги на одну закупку или текущие расходы. Получаете всю сумму сразу.',
    reason: 'Подходит для разовой закупки: понятная сумма и фиксированный график.',
    min: 100000,
    max: 5000000,
    minTerm: 3,
    maxTerm: 24,
  },
  R02: {
    description: 'Общий лимит для регулярных закупок. Возвращённые деньги можно взять снова.',
    reason: 'Подходит для закупок каждый месяц: лимит восстанавливается после погашения.',
    min: 100000,
    max: 5000000,
    minTerm: 3,
    maxTerm: 24,
  },
  R03: {
    description: 'Резерв на расчётном счёте, когда платить нужно раньше поступления выручки.',
    reason: 'Подходит для кассового разрыва: погашение из поступлений на счёт.',
    min: 100000,
    max: 5000000,
    minTerm: 3,
    maxTerm: 24,
  },
};
export const recommendedProduct: Record<Need, Product> = {
  once: 'R01',
  recurring: 'R02',
  gap: 'R03',
};
export const purposeOptions = [
  'Закупка товара',
  'Пополнение оборотных средств',
  'Оплата поставщикам',
  'Покрытие кассового разрыва',
  'Другая оборотная цель',
];
export function backendProduct(family: string, id: string): Product | undefined {
  if (id === 'term' || family === 'WORKING_CAPITAL_TERM_LOAN') return 'R01';
  if (
    id === 'rcl' ||
    id === 'credit_line' ||
    id === 'revolver' ||
    family === 'REVOLVING_CREDIT_LINE'
  )
    return 'R02';
  if (id === 'overdraft' || family === 'OVERDRAFT') return 'R03';
}
