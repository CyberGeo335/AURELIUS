import { useState } from 'react';
import type { QuestionV2 } from '../api/HttpV2Api';
import { Action, ErrorState } from '../components/v2/primitives';

export function parseFieldValue(field: QuestionV2, text: string): string | number | boolean {
  if (!text.trim()) throw new Error(`${field.label}: укажите значение.`);
  if (field.data_type === 'boolean') {
    if (!['true', 'false'].includes(text))
      throw new Error(`${field.label}: выберите «Да» или «Нет».`);
    return text === 'true';
  }
  if (['integer', 'bigint', 'smallint'].includes(field.data_type)) {
    if (!/^-?\d+$/.test(text) || !Number.isSafeInteger(Number(text)))
      throw new Error(`${field.label}: требуется целое число.`);
    return Number(text);
  }
  return text;
}
const valueText = (value: unknown) =>
  value == null ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
function ValueInput({
  field,
  value,
  onChange,
  disabled,
  required = false,
}: {
  field: QuestionV2;
  value: string;
  onChange: (value: string) => void;
  disabled: boolean;
  required?: boolean;
}) {
  return field.data_type === 'boolean' ? (
    <select
      required={required}
      disabled={disabled}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Выберите значение</option>
      <option value="true">Да</option>
      <option value="false">Нет</option>
    </select>
  ) : (
    <input
      disabled={disabled}
      required={required}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      type={field.data_type === 'date' ? 'date' : 'text'}
      inputMode={
        ['integer', 'bigint', 'smallint'].includes(field.data_type) ? 'numeric' : undefined
      }
    />
  );
}
export function QuestionnaireV2({
  questions,
  version,
  editable,
  busy,
  save,
}: {
  questions: QuestionV2[];
  version: number;
  editable: boolean;
  busy: boolean;
  save: (
    answers: { product_code: string; field_code: string; value: unknown }[],
    version: number,
  ) => Promise<boolean>;
}) {
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [base, setBase] = useState<number | null>(null);
  const [error, setError] = useState('');
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setError('');
        try {
          const answers = questions
            .filter(
              (q) =>
                q.editable &&
                drafts[q.field_code] !== undefined &&
                drafts[q.field_code] !== valueText(q.value),
            )
            .map((q) => ({
              product_code: q.product_code,
              field_code: q.field_code,
              value: parseFieldValue(q, drafts[q.field_code]),
            }));
          if (!answers.length) {
            setError('Изменений для сохранения нет.');
            return;
          }
          if (await save(answers, base ?? version)) {
            setDrafts({});
            setBase(null);
          }
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      {questions.map((q) => (
        <label
          key={q.product_code + q.field_code}
          className="form-field"
          style={{ marginBottom: 12 }}
        >
          {q.label} · {q.status} · {q.source}
          {q.source_ref && (
            <span className="small muted">
              Источник: {q.source_ref}
              {q.available_at ? ' · ' + new Date(q.available_at).toLocaleString('ru-RU') : ''}
            </span>
          )}
          {q.validation_error && <span role="alert">{q.validation_error}</span>}
          {q.editable && editable ? (
            <ValueInput
              field={q}
              value={drafts[q.field_code] ?? valueText(q.value)}
              disabled={busy}
              onChange={(value) => {
                setBase((current) => current ?? version);
                setDrafts((current) => ({ ...current, [q.field_code]: value }));
              }}
            />
          ) : (
            <span>{q.value == null ? 'Не указано' : String(q.value)}</span>
          )}
        </label>
      ))}
      {editable && <Action disabled={busy}>Сохранить ответы</Action>}
      <ErrorState message={error} />
    </form>
  );
}
export function VerifyFieldV2({
  questions,
  version,
  enabled,
  busy,
  save,
}: {
  questions: QuestionV2[];
  version: number;
  enabled: boolean;
  busy: boolean;
  save: (arguments_: Record<string, unknown>, version: number) => Promise<boolean>;
}) {
  const fields = questions.filter((q) => q.editable);
  const [code, setCode] = useState(''),
    [value, setValue] = useState(''),
    [source, setSource] = useState(''),
    [error, setError] = useState('');
  const [base, setBase] = useState<number | null>(null);
  const field = fields.find((q) => q.field_code === code);
  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setError('');
        try {
          if (!field) throw new Error('Выберите поле из досье.');
          if (
            await save(
              {
                field_code: field.field_code,
                value: parseFieldValue(field, value),
                source_ref: source,
              },
              base ?? version,
            )
          ) {
            setBase(null);
            setSource('');
          }
        } catch (e) {
          setError((e as Error).message);
        }
      }}
    >
      <label className="form-field">
        Поле для проверки
        <select
          required
          disabled={busy || !enabled}
          value={code}
          onChange={(e) => {
            setCode(e.target.value);
            setValue(valueText(fields.find((q) => q.field_code === e.target.value)?.value));
            setBase(version);
          }}
        >
          <option value="">Выберите поле</option>
          {fields.map((q) => (
            <option key={q.field_code} value={q.field_code}>
              {q.field_code} · {q.label} ({q.data_type})
            </option>
          ))}
        </select>
      </label>
      {field && (
        <label className="form-field">
          Проверенное значение
          <ValueInput
            field={field}
            value={value}
            onChange={setValue}
            disabled={busy || !enabled}
            required
          />
        </label>
      )}
      <label className="form-field">
        Источник проверки
        <input
          required
          disabled={busy || !enabled}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        />
      </label>
      <Action disabled={busy || !enabled}>Подтвердить поле</Action>
      <ErrorState message={error} />
    </form>
  );
}
