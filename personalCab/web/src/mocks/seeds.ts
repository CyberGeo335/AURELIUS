import type { Application, Company, CreditState, Product } from '../domain/types';
import { defaultFields } from '../domain/forms';
export const companies: Company[] = [
  {
    id: 'karpov',
    entity: 'IP',
    name: 'ИП Карпов Илья Сергеевич',
    inn: '771234567890',
    registration: '321774600123456',
    registered: '2024-06-14',
    okved: '47.29 — розничная торговля продуктами',
    flow: 296000,
    existing: 38000,
    monthly: [1.21, 1.25, 1.48, 0.98, 0.86, 1.05, 1.12, 1.18, 1.15, 1.1, 1.19, 1.33],
  },
  {
    id: 'zerno',
    entity: 'OOO',
    name: 'ООО «Зерно Опт»',
    inn: '7701234567',
    registration: '1257700123456',
    registered: '2025-03-02',
    okved: '46.37 — оптовая торговля кофе',
    flow: 330000,
    existing: 60000,
    monthly: [2.7, 2.8, 3.1, 2.4, 2.2, 2.6, 2.9, 3.2, 2.8, 3, 3.1, 3.1],
  },
  {
    id: 'ahmedova',
    entity: 'IP',
    name: 'ИП Ахмедова Л. Р.',
    inn: '771234567891',
    registration: '321774600123457',
    registered: '2023-03-01',
    okved: '47.11',
    flow: 180000,
    existing: 20000,
    monthly: [0.8, 0.9, 0.7, 0.8, 0.9, 0.8, 0.9, 0.8, 0.9, 0.7, 0.8, 0.9],
  },
  {
    id: 'bakery',
    entity: 'OOO',
    name: 'ООО «Пекарня на Садовой»',
    inn: '7701234568',
    registration: '1257700123457',
    registered: '2024-02-01',
    okved: '10.71',
    flow: 550000,
    existing: 60000,
    monthly: [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3],
  },
  {
    id: 'kim',
    entity: 'IP',
    name: 'ИП Ким Д. А.',
    inn: '771234567892',
    registration: '321774600123458',
    registered: '2022-05-01',
    okved: '47.11',
    flow: 160000,
    existing: 15000,
    monthly: [0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7],
  },
  {
    id: 'potok',
    entity: 'OOO',
    name: 'ООО «Поток»',
    inn: '7701234569',
    registration: '1257700123458',
    registered: '2021-01-01',
    okved: '46.90',
    flow: 243151,
    existing: 20000,
    monthly: [2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2, 2],
  },
];
export function makeDraft(
  company: Company,
  product: Product,
  id: string,
  now: number,
): Application {
  return {
    id,
    companyId: company.id,
    product,
    amount: company.entity === 'OOO' ? 3000000 : 1500000,
    term: company.entity === 'OOO' ? 18 : 12,
    purpose: 'Закупка товара',
    status: 'DRAFT',
    stage: 0,
    revision: 1,
    created: now,
    updated: now,
    scenario: 'normal',
    externalWait: false,
    fields: defaultFields(company, product),
    sources: {},
    flow: company.flow,
    existing: company.existing,
    leasing: null,
    businessConfirmed: false,
    statement: false,
    consentBki: false,
    consentData: false,
    offers: [],
    requests: [],
    history: [],
    revisions: [],
    reason: '',
    reasonCode: '',
    step: 0,
    files: [],
  };
}
export function seedState(now = Date.now()): CreditState {
  const specs = [
    ['karpov', 'R01', '00142', 1500000, 12, 'NEEDS_INFO'],
    ['zerno', 'R01', '00151', 3000000, 18, 'MANUAL_REVIEW'],
    ['ahmedova', 'R01', '00149', 800000, 12, 'MANUAL_REVIEW'],
    ['bakery', 'R02', '00012', 5000000, 24, 'MANUAL_REVIEW'],
    ['kim', 'R03', '00007', 600000, 12, 'NEEDS_INFO'],
    ['potok', 'R01', '00138', 2000000, 24, 'OFFERED'],
  ] as const;
  const applications = specs.map(([companyId, product, num, amount, term, status]) => {
    const company = companies.find((c) => c.id === companyId)!;
    const a = makeDraft(company, product, `${product}-2026-${num}`, now - 720000);
    Object.assign(a, {
      amount,
      term,
      status,
      stage: status === 'MANUAL_REVIEW' ? 4 : status === 'OFFERED' ? 5 : 2,
      statement: true,
      businessConfirmed: true,
      consentBki: true,
      consentData: true,
      consentVersion: 'bki-demo-2026.10-v1',
      consentedAt: now - 720000,
      leasing: companyId === 'karpov' ? null : true,
      revision: companyId === 'zerno' ? 3 : 1,
    });
    a.fields[`${product}_05`] = String(amount);
    a.fields[`${product}_06`] = String(term);
    a.fields[`${product}_31`] = 'Подтверждаю';
    a.reason =
      companyId === 'zerno'
        ? 'Покрытие ниже минимума 1,3×; выручка в источниках расходится на 12%'
        : companyId === 'ahmedova'
          ? 'Выписка и декларация расходятся на 18%'
          : companyId === 'bakery'
            ? 'Доверенность представителя не подтверждена'
            : '';
    a.reasonCode =
      companyId === 'zerno'
        ? 'DSCR_BELOW_MIN, DATA_CONFLICT'
        : companyId === 'bakery'
          ? 'AUTHORITY_UNVERIFIED'
          : 'DATA_CONFLICT';
    if (status === 'NEEDS_INFO')
      a.requests = [
        {
          id: `request-${num}`,
          field: companyId === 'karpov' ? 'leasing' : 'statement',
          text:
            companyId === 'karpov'
              ? '38 000 ₽ в месяц — это лизинг?'
              : 'Загрузите выписку за последние 3 месяца',
          state: 'OPEN',
        },
      ];
    if (status === 'OFFERED')
      a.offers = [
        {
          id: `offer-${num}`,
          amount,
          term,
          expires: now + 6 * 86400000,
          revision: a.revision,
          kind: 'OFFER',
          label: 'Одобрено',
        },
      ];
    a.history = [
      {
        id: `event-${num}`,
        at: now - 720000,
        actor: 'Система · демо',
        text:
          status === 'MANUAL_REVIEW'
            ? a.reason
            : status === 'NEEDS_INFO'
              ? 'Запросили уточнение у клиента'
              : 'Подготовили предложение',
        revision: a.revision,
        model: 'score-model v0.3',
        policy: 'policy-2026.10',
        snapshot: `FS-${a.id}-${a.revision}`,
      },
    ];
    return a;
  });
  return { version: 1, companies, applications };
}
