import { afterEach, expect, it, vi } from 'vitest';
import { fireEvent, screen, within } from '@testing-library/react';
import { application, mountQueueForm } from './queueFormFixtures';
import { durationLabel, firstDecisionAverage, lastQueueEvent } from '../domain/httpQueue';
import type { ServerApplication } from '../domain/types';

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
});
const assessment = { risk_assessment: { pd_application_1y: 0.1, pd_limit_1y: 0.2 } };
const history = (start: string, end: string) => [
  { event_id: 1, action: 'submit', created_at: start },
  { event_id: 2, action: 'review', created_at: end },
  { event_id: 3, action: 'review', created_at: '2026-10-27T12:00:00Z' },
];
const assigned = {
  employee_id: 10,
  first_name: 'Иван',
  last_name: 'Иванов',
  assigned_at: '2026-10-26',
};
function apps(): ServerApplication[] {
  return [
    application(1, {
      application_status: 'UNDER_REVIEW',
      assessment,
      assignment: assigned,
      history: [{ event_id: 1, action: 'submit', created_at: '2026-10-26T08:00:00Z' }],
    }),
    application(2, { application_status: 'UNDER_REVIEW', company_id: 124 }),
    application(3, {
      application_status: 'AWAITING_DATA',
      assignment: assigned,
      requests: [
        {
          request_id: 1,
          field_code: 'R01_05',
          question_text: 'Уточните сумму',
          request_status: 'OPEN',
          answer_value: null,
        },
      ],
    }),
    application(4, {
      application_status: 'APPROVED',
      assessment: { risk_assessment: { pd_application_1y: 0.3, pd_limit_1y: 0.2 } },
      history: history('2026-10-26T08:00:00Z', '2026-10-26T09:00:00Z'),
    }),
    application(5, {
      application_status: 'REJECTED',
      history: history('2026-10-26T08:00:00Z', '2026-10-26T08:30:00Z'),
    }),
    application(6, { application_status: 'CANCELLED', application_date: '2026-10-20T08:00:00Z' }),
    application(7),
    application(8, {
      application_status: 'UNDER_REVIEW',
      assessment,
      offer_stale: { reason: 'Изменились данные' },
      fields: [
        {
          field_code: 'R01_03',
          field_value: '7701000000',
          value_source: 'FNS',
          verification_status: 'CONFLICT',
        },
      ],
      reasons: [{ code: 'DB_INPUTS_UNAVAILABLE', message: 'Database input unavailable' }],
    }),
    application(9, {
      application_status: 'UNDER_REVIEW',
      assessment,
      requests: [
        {
          request_id: 2,
          field_code: 'R01_03',
          question_text: 'Уточнение',
          request_status: 'OPEN',
          answer_value: null,
        },
      ],
    }),
  ];
}
const table = () => screen.getByRole('table', { name: 'Заявки банка' });
const row = (id: number) => within(table()).getByText(`№ ${id}`).closest('tr')!;
it('counts real queue states, excludes drafts and computes the first employee decision average', async () => {
  await mountQueueForm('/bank', apps());
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
    '1 заявка ждёт вашего решения',
  );
  expect(screen.getByText('заявок в очереди').closest('.key-value')).toHaveTextContent('8');
  expect(screen.getByText('ждут ответа клиента').closest('.key-value')).toHaveTextContent('2');
  expect(
    screen.getByText('в среднем до первого решения сотрудника').closest('.key-value'),
  ).toHaveTextContent('45 мин');
  expect(within(table()).queryByText('№ 7')).toBeNull();
  expect(screen.getByRole('link', { name: 'Разобрать первую' })).toHaveAttribute(
    'href',
    '/bank/applications/1',
  );
  expect(row(1)).toHaveClass('attention-row');
  expect(row(8)).not.toHaveClass('attention-row');
  expect(screen.queryByText(/решено автоматически/i)).toBeNull();
  expect(
    within(table())
      .getAllByRole('columnheader')
      .map((e) => e.textContent),
  ).toEqual([
    'Заявка и клиент',
    'Продукт и сумма',
    'Этап',
    'PD 12 мес.',
    'Что требует внимания',
    'Ждёт',
    'Ответственный',
    'Действие',
  ]);
});
it('uses status pills, preserves counters during search and sorts oldest last-action time first', async () => {
  await mountQueueForm('/bank', apps());
  expect(within(table()).getAllByRole('row')[1]).toHaveTextContent('№ 6');
  for (const [label, count] of [
    ['Ждут решения', 1],
    ['Проверяются', 2],
    ['Нужны данные', 2],
    ['Одобрено', 1],
    ['Отказ', 1],
    ['Отменена', 1],
  ] as const) {
    fireEvent.click(screen.getByRole('button', { name: `${label} ${count}` }));
    expect(within(table()).getAllByRole('row')).toHaveLength(count + 1);
  }
  fireEvent.click(screen.getByRole('button', { name: 'Все 8' }));
  fireEvent.change(screen.getByLabelText('Поиск заявки'), { target: { value: 'дРУГОЙ БИзнес' } });
  expect(within(table()).getAllByRole('row')).toHaveLength(2);
  expect(row(2)).toBeInTheDocument();
  expect(screen.getByText('заявок в очереди').closest('.key-value')).toHaveTextContent('8');
  fireEvent.change(screen.getByLabelText('Поиск заявки'), { target: { value: '  9  ' } });
  expect(row(9)).toBeInTheDocument();
});
it('shows PD comparisons, absent scores, factual attention and real assignment', async () => {
  await mountQueueForm('/bank', apps());
  expect(row(1)).toHaveTextContent('10%');
  expect(row(1)).toHaveTextContent('В лимите · 20%');
  expect(row(4)).toHaveTextContent('Выше лимита · 20%');
  expect(row(2)).toHaveTextContent('Нет оценки');
  expect(row(8)).toHaveTextContent('1 конфликт в полях');
  expect(row(8)).toHaveTextContent('Устаревшее предложение: Изменились данные');
  expect(row(8)).toHaveTextContent('DB_INPUTS_UNAVAILABLE');
  expect(row(8)).toHaveTextContent('Database input unavailable');
  expect(row(8)).toHaveTextContent('Предыдущая оценка');
  expect(row(3)).toHaveTextContent('Открыто: 1 запрос');
  expect(row(1)).toHaveTextContent('Иван Иванов (ID 10)');
  expect(row(2)).toHaveTextContent('Не назначен');
});
it('limits the entire My reviews summary and table to the current assignee', async () => {
  await mountQueueForm('/bank/mine', apps());
  expect(within(table()).getAllByRole('row')).toHaveLength(3);
  expect(screen.getByText('заявок в очереди').closest('.key-value')).toHaveTextContent('2');
  expect(screen.getByText('Пока нет решений')).toBeInTheDocument();
});
it('does not invent missing amounts, terms, PD limits or elapsed time', async () => {
  vi.spyOn(Date, 'now').mockReturnValue(Date.parse('2026-10-26T10:00:00Z'));
  await mountQueueForm('/bank', [
    application(1, {
      application_status: 'UNDER_REVIEW',
      requested_amount: null,
      requested_term_months: null,
      application_date: 'bad-date',
      assessment: { risk_assessment: { pd_application_1y: 0 } },
    }),
  ]);
  expect(row(1)).toHaveTextContent('Сумма не указана · Срок не указан');
  expect(row(1)).toHaveTextContent('0%');
  expect(row(1)).toHaveTextContent('Лимит не указан');
  expect(row(1).querySelector('td:nth-child(6)')).toHaveTextContent('—');
});
it('handles absent and invalid event pairs without manufacturing an average', async () => {
  const { api } = await mountQueueForm('/bank', [
    application(1, {
      application_status: 'CANCELLED',
      history: [{ event_id: 1, action: 'review', created_at: 'bad' }],
    }),
  ]);
  expect(screen.getByText('Пока нет решений')).toBeInTheDocument();
  expect(firstDecisionAverage(api.getSnapshot().applications)).toBeUndefined();
  expect(lastQueueEvent(api.getSnapshot().applications[0])).toBe(
    Date.parse('2026-10-26T08:00:00Z'),
  );
  expect(durationLabel(0)).toBe('Менее минуты');
  expect(durationLabel(-1)).toBe('—');
  expect(durationLabel(7200000)).toBe('2 ч');
  expect(durationLabel(259200000)).toBe('3 дн');
});
