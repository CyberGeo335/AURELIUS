import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { VerifyFieldV2, QuestionnaireV2 } from '../app/CaseFormsV2';

it('shows the actual source and a source-format conflict without replacing the value', () => {
  render(
    <QuestionnaireV2
      version={5}
      editable
      busy={false}
      save={vi.fn()}
      questions={[
        {
          field_code: 'R01_03',
          product_code: 'R01',
          label: 'ИНН',
          data_type: 'text',
          value: '1234567890',
          editable: true,
          status: 'CONFLICT',
          source: 'DATABASE',
          source_ref: 'snapshot:1:R01_03',
          validation_error: 'Нужен ИНН ИП из 12 цифр.',
        },
      ]}
    />,
  );
  expect(screen.getByRole('alert')).toHaveTextContent('Нужен ИНН ИП из 12 цифр.');
  expect(screen.getByText('Источник: snapshot:1:R01_03')).toBeInTheDocument();
  expect(screen.getByLabelText(/^ИНН/)).toHaveValue('1234567890');
});

it.each([
  { data_type: 'boolean', input: 'false', expected: false },
  { data_type: 'boolean', input: 'true', expected: true },
  { data_type: 'integer', input: '23', expected: 23 },
])(
  'sends a typed $data_type value ($input) from the operator form',
  async ({ data_type, input, expected }) => {
    const save = vi.fn().mockResolvedValue(true);
    render(
      <VerifyFieldV2
        version={5}
        enabled
        busy={false}
        save={save}
        questions={[
          {
            field_code: 'R01_TEST',
            product_code: 'R01',
            label: 'Проверяемое поле',
            data_type,
            value: null,
            editable: true,
            status: 'MISSING',
            source: 'CLIENT',
          },
        ]}
      />,
    );
    fireEvent.change(screen.getByLabelText(/^Поле для проверки/), {
      target: { value: 'R01_TEST' },
    });
    fireEvent.change(screen.getByLabelText(/^Проверенное значение/), { target: { value: input } });
    fireEvent.change(screen.getByLabelText('Источник проверки'), {
      target: { value: 'Synthetic explicit review' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить поле' }));
    await waitFor(() =>
      expect(save).toHaveBeenCalledWith(
        { field_code: 'R01_TEST', value: expected, source_ref: 'Synthetic explicit review' },
        5,
      ),
    );
  },
);
