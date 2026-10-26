import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { vi } from 'vitest';
import { Providers } from '../app/context';
import { App } from '../app/App';
import { HttpCreditApi } from '../api/HttpCreditApi';
import type { Product, ServerApplication, ServerRequirement } from '../domain/types';

export function requirements(product: Product = 'R01'): ServerRequirement[] {
  const ipOnly = [10, 13],
    legalOnly = [9, 11, 12, 14, 19, 27, 28];
  const targets: Record<number, string> = {
    1: 'credit_applications.product_code',
    2: 'companies.entity_type',
    3: 'companies.inn',
    4: 'credit_applications.purpose',
    5: 'credit_applications.requested_amount',
    6: 'credit_applications.requested_term_days',
    24: 'application_details.contact_full_name',
    25: 'application_details.contact_role',
    26: 'application_details.contact_phone',
    29: 'application_details.signer_full_name',
    30: 'application_details.signer_authority_basis',
  };
  return Array.from({ length: product === 'R01' ? 31 : 34 }, (_, index) => {
    const n = index + 1;
    return {
      product_code: product,
      field_code: `${product}_${String(n).padStart(2, '0')}`,
      field_number: n,
      field_label: `Поле ${n}`,
      required_ip: !legalOnly.includes(n),
      required_ooo: !ipOnly.includes(n),
      target_db_field: targets[n] ?? `companies.field_${n}`,
      format_rule: null,
    };
  });
}
export function application(id = 1, patch: Partial<ServerApplication> = {}): ServerApplication {
  const product = patch.product_code ?? 'R01';
  const values: Record<number, string> = {
    1: product,
    2: 'Юридическое лицо',
    3: '7701000000',
    4: 'Закупка товаров',
    5: '3000000',
    6: '36',
    31: 'Подтверждаю',
    32: product === 'R03' ? '40702810000000000001' : '30',
    33: product === 'R03' ? 'Банк счёта' : '12',
    34: product === 'R03' ? '044525000' : 'Да',
  };
  return {
    application_id: id,
    company_id: 123,
    product_code: product,
    requested_amount: '3000000',
    requested_term_months: 36,
    purpose: 'Закупка товаров',
    application_status: 'DRAFT',
    application_date: '2026-10-26T08:00:00Z',
    version: 1,
    form_state: { step: 0, businessConfirmed: true, consentData: true, consentBki: true },
    decision: undefined,
    offer: null,
    reasons: [],
    assessment: null,
    fields: requirements(product).map((r) => ({
      field_code: r.field_code,
      field_value: values[r.field_number] ?? `Значение ${r.field_number}`,
      verification_status: 'UNVERIFIED',
      value_source: 'CLIENT',
    })),
    requests: [],
    history: [],
    details: null,
    product_details:
      product === 'R01' ? null : { max_tranche_term_value: 30, max_tranche_term_unit: 'DAYS' },
    ...patch,
  };
}
export async function mountQueueForm(
  path: string,
  initial: ServerApplication[],
  rows = requirements(),
  entity = 'LEGAL_ENTITY',
) {
  vi.stubEnv('VITE_API_MODE', 'http');
  let apps = structuredClone(initial);
  const commands: Record<string, unknown>[] = [];
  let handler: ((body: Record<string, unknown>) => Response | undefined) | undefined;
  const api = new HttpCreditApi();
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith('session'))
        return Response.json({
          user_id: 10,
          login: 'fixture',
          first_name: 'Иван',
          last_name: 'Иванов',
          role: path.startsWith('/bank') ? 'BANK_EMPLOYEE' : 'CLIENT',
          company_id: path.startsWith('/bank') ? null : 123,
        });
      if (url.endsWith('action')) {
        const body = JSON.parse(String(options?.body));
        commands.push(body);
        const response = handler?.(body);
        if (response) return response;
        apps = apps.map((a) => {
          if (a.application_id !== body.application_id) return a;
          const p = body.patch ?? {};
          const form_state = { ...a.form_state };
          for (const key of ['step', 'businessConfirmed', 'consentData', 'consentBki'])
            if (key in p) form_state[key] = p[key];
          return {
            ...a,
            version: a.version + 1,
            application_status: body.action === 'submit' ? 'UNDER_REVIEW' : a.application_status,
            form_state,
            requested_amount: p.amount != null ? String(p.amount) : a.requested_amount,
            requested_term_months: p.term ?? a.requested_term_months,
            purpose: p.purpose ?? a.purpose,
            fields: p.fields
              ? Object.entries(p.fields).map(([field_code, field_value]) => ({
                  field_code,
                  field_value,
                  value_source: 'CLIENT',
                  verification_status: 'UNVERIFIED',
                }))
              : a.fields,
            details: { ...a.details, ...p.details },
            product_details: { ...a.product_details, ...p.product_details },
          };
        });
        return Response.json({ application_id: String(body.application_id) });
      }
      return Response.json({
        companies: [
          { company_id: 123, name: 'Первая компания', inn: '7701000000', entity_type: entity },
          {
            company_id: 124,
            name: 'Другой бизнес',
            inn: '7702000000',
            entity_type: 'LEGAL_ENTITY',
          },
        ],
        applications: apps,
        requirements: rows,
        catalog: [],
      });
    }),
  );
  render(
    <MemoryRouter initialEntries={[path]}>
      <Providers api={api}>
        <App />
      </Providers>
    </MemoryRouter>,
  );
  await screen.findByRole('heading', {
    name: path.startsWith('/bank')
      ? path.endsWith('/mine')
        ? 'Мои разборы'
        : 'Очередь'
      : 'Анкета',
  });
  return {
    api,
    commands,
    setApps: (next: ServerApplication[]) => {
      apps = next;
    },
    setHandler: (next: typeof handler) => {
      handler = next;
    },
  };
}
