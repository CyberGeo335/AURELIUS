import { Check } from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Link, useNavigate } from 'react-router';
import { useApi, useAction } from '../app/context';
import { HttpCreditApi } from '../api/HttpCreditApi';
import { Action, Card, ErrorState, SourceBadge } from '../components/v2/primitives';
import { Input } from '../components/ui/input';
import { AssistantDraftCard } from './HttpAssistant';
import { money } from '../domain/finance';
import { sourceLabel } from '../domain/provenance';
import {
  consentLabels,
  fieldStep,
  formMissing,
  formStepTitles,
  initialFields,
  restoredFormStep,
} from '../domain/formSteps';
import { products, type Application, type Company, type ServerRequirement } from '../domain/types';

function confirmationVersion(app: Application) {
  return Math.max(
    0,
    ...(app.server?.history ?? [])
      .filter((event) => event.action === 'confirm_facts')
      .map((event) => event.event_id),
  );
}
function draftAmount(value: unknown) {
  return value != null &&
    String(value).trim() &&
    Number.isFinite(Number(value)) &&
    Number(value) > 0
    ? money(Number(value))
    : 'Сумма не указана';
}
export function DraftForm({
  app,
  company,
  rows,
  children,
}: {
  app: Application;
  company: Company;
  rows: ServerRequirement[];
  children?: ReactNode;
}) {
  const api = useApi() as HttpCreditApi;
  const nav = useNavigate();
  const action = useAction();
  const [values, setValues] = useState(() => initialFields(rows, app, company));
  const [consents, setConsents] = useState({
    consentBki: app.consentBki,
    consentData: app.consentData,
    businessConfirmed: app.businessConfirmed,
  });
  const [tranche, setTranche] = useState(
    String(app.server?.product_details?.max_tranche_term_value ?? ''),
  );
  const [unit, setUnit] = useState(
    String(app.server?.product_details?.max_tranche_term_unit ?? ''),
  );
  const [saved, setSaved] = useState(false);
  const [formVersion, setFormVersion] = useState(app.revision);
  const missing = formMissing(rows, app.product, values, consents, tranche, unit);
  const [step, setStep] = useState(() => restoredFormStep(app.step, missing));
  const [assistantApplied, setAssistantApplied] = useState(false);
  const baseline = useRef({
    values: { ...values },
    tranche,
    unit,
    consents: { ...consents },
    confirmation: confirmationVersion(app),
  });
  const total = rows.length + 3 + (app.product === 'R01' ? 0 : 2);
  const completeness = Math.round(((total - missing.length) / total) * 100);
  const canVisit = (target: number) =>
    target <= step || !missing.some((item) => item.step < target);
  useEffect(() => {
    const incoming = initialFields(rows, app, company);
    const nextTranche = String(app.server?.product_details?.max_tranche_term_value ?? '');
    const nextUnit = String(app.server?.product_details?.max_tranche_term_unit ?? '');
    const nextConsents = {
      businessConfirmed: app.businessConfirmed,
      consentData: app.consentData,
      consentBki: app.consentBki,
    };
    const next = {
      values: incoming,
      tranche: nextTranche,
      unit: nextUnit,
      consents: nextConsents,
      confirmation: confirmationVersion(app),
    };
    const previous = baseline.current;
    const keys = [...new Set([...Object.keys(previous.values), ...Object.keys(incoming)])];
    const unchanged =
      keys.every((key) => incoming[key] === previous.values[key]) &&
      nextTranche === previous.tranche &&
      nextUnit === previous.unit &&
      consentLabels.every(([key]) => nextConsents[key] === previous.consents[key]);
    if (app.revision === formVersion || unchanged) {
      baseline.current = next;
      if (app.revision > formVersion) setFormVersion(app.revision);
      return;
    }
    if (app.revision > formVersion && next.confirmation > previous.confirmation) {
      setValues((local) => {
        const merged = { ...local };
        for (const key of keys)
          if (incoming[key] !== previous.values[key]) merged[key] = incoming[key] ?? '';
        return merged;
      });
      if (nextTranche !== previous.tranche) setTranche(nextTranche);
      if (nextUnit !== previous.unit) setUnit(nextUnit);
      setConsents((local) => {
        const merged = { ...local };
        for (const [key] of consentLabels)
          if (nextConsents[key] !== previous.consents[key]) merged[key] = nextConsents[key];
        return merged;
      });
      baseline.current = next;
      setFormVersion(app.revision);
      setAssistantApplied(true);
      setSaved(false);
    }
  }, [app, company, rows, formVersion]);
  const code = (n: number) => `${app.product}_${String(n).padStart(2, '0')}`;
  const save = async (nextStep = step) => {
    const details: Record<string, unknown> = {};
    for (const [n, key] of [
      [24, 'contact_full_name'],
      [25, 'contact_role'],
      [26, 'contact_phone'],
      [29, 'signer_full_name'],
      [30, 'signer_authority_basis'],
    ] as const) {
      if (values[code(n)]) details[key] = values[code(n)];
    }
    const product_details: Record<string, unknown> = {};
    if (app.product !== 'R01') {
      if (tranche) product_details.max_tranche_term_value = Number(tranche);
      if (unit) product_details.max_tranche_term_unit = unit;
    }
    if (app.product === 'R03')
      for (const [n, key] of [
        [32, 'overdraft_account_ref'],
        [33, 'overdraft_bank_name'],
        [34, 'overdraft_bank_bik'],
      ] as const) {
        if (values[code(n)]) product_details[key] = values[code(n)];
      }
    if (app.product === 'R02' && values[code(33)])
      product_details.drawdown_period_months = Number(values[code(33)]);
    await api.command('save', app.id, {
      expected_version: formVersion,
      patch: {
        fields: values,
        step: nextStep,
        details,
        product_details,
        ...consents,
        ...(values[code(5)] ? { amount: values[code(5)] } : {}),
        ...(values[code(6)] ? { term: Number(values[code(6)]) } : {}),
        purpose: values[code(4)],
      },
    });
    setFormVersion(
      api.getSnapshot().applications.find((item) => item.id === app.id)?.revision ?? formVersion,
    );
    setSaved(true);
  };
  const goStep = (target: number) => {
    if (target === step || !canVisit(target)) return;
    void action.run(async () => {
      if (target > step) await save(target);
      else {
        await api.command('save', app.id, {
          expected_version: formVersion,
          patch: { step: target },
        });
        setFormVersion(
          api.getSnapshot().applications.find((item) => item.id === app.id)?.revision ??
            formVersion,
        );
      }
      setStep(target);
    });
  };
  const amount = values[code(5)] ?? app.server?.requested_amount;
  const term = values[code(6)] ?? app.server?.requested_term_months;
  const purpose = values[code(4)] ?? app.purpose;
  return (
    <div className="http-form">
      <Link className="back-link" to="/client/applications">
        ← Все заявки
      </Link>
      <div className="form-layout">
        <aside className="vertical-steps" aria-label="Шаги анкеты">
          {formStepTitles.map((title, index) => (
            <button
              key={title}
              type="button"
              disabled={action.busy || !canVisit(index)}
              aria-current={step === index ? 'step' : undefined}
              data-complete={
                index < step && !missing.some((item) => item.step === index) ? 'true' : undefined
              }
              onClick={() => goStep(index)}
            >
              <span>
                {index < step && !missing.some((item) => item.step === index) ? (
                  <Check aria-hidden size={18} />
                ) : (
                  index + 1
                )}
              </span>
              {title}
            </button>
          ))}
        </aside>
        <div className="http-form-main">
          <div className="http-form-heading">
            <p className="muted">
              Новая заявка № {app.id} · {company.name}
            </p>
            <h1>{products[app.product]}</h1>
          </div>
          <AssistantDraftCard app={app} />
          {assistantApplied && (
            <p role="status">
              Подтверждённые изменения помощника применены. Остальные ваши правки сохранены.
            </p>
          )}
          {app.revision !== formVersion && (
            <Card>
              <p role="status">
                Сохранённая заявка изменилась. Ваш ввод остаётся в форме; старая версия не
                перезапишет изменения из диалога или другой вкладки.
              </p>
              <p>
                Сохранено: {draftAmount(app.server?.requested_amount)} ·{' '}
                {app.server?.requested_term_months == null
                  ? 'Срок не указан'
                  : `${app.server.requested_term_months} мес.`}{' '}
                · Цель: {app.purpose || 'Не указана'}.
              </p>
              <Action
                type="button"
                tone="outline"
                disabled={action.busy}
                onClick={() => {
                  setValues(initialFields(rows, app, company));
                  setConsents({
                    consentBki: app.consentBki,
                    consentData: app.consentData,
                    businessConfirmed: app.businessConfirmed,
                  });
                  setTranche(String(app.server?.product_details?.max_tranche_term_value ?? ''));
                  setUnit(String(app.server?.product_details?.max_tranche_term_unit ?? ''));
                  setFormVersion(app.revision);
                  setSaved(false);
                }}
              >
                Заменить мой ввод сохранённой версией
              </Action>
            </Card>
          )}
          <form
            noValidate
            onSubmit={(event) => {
              event.preventDefault();
              if (step !== 4 || missing.length) return;
              void action.run(async () => {
                await save();
                await api.submit(app.id);
                nav(`/client/applications/${app.id}`);
              });
            }}
          >
            <Card>
              <h2>Анкета</h2>
              <h3>{formStepTitles[step]}</h3>
              <p className="muted">
                Проверьте реквизиты и укажите параметры запроса. Источники указаны для сохранённых
                значений.
              </p>
              {[0, 1, 2, 3].map((index) => (
                <fieldset
                  key={index}
                  data-form-step={index}
                  hidden={step !== index}
                  disabled={action.busy || step !== index}
                  className="business-fields"
                >
                  <legend className="sr-only">{formStepTitles[index]}</legend>
                  {rows
                    .filter((row) => fieldStep(row, app.product) === index)
                    .map((r) => {
                      const value = values[r.field_code] ?? '';
                      const knownCompanyFact =
                        r.target_db_field.startsWith('companies.') &&
                        r.target_db_field.split(/\s*\+\s*/).every((part) => {
                          const key = part.replace(/^companies\./, '');
                          return (
                            company.server?.[key] !== null &&
                            company.server?.[key] !== undefined &&
                            company.server?.[key] !== ''
                          );
                        });
                      const readOnly = [1, 2].includes(r.field_number) || knownCompanyFact;
                      return (
                        <label className="form-field" key={r.field_code}>
                          {r.field_label}
                          {r.field_number === 31 ? (
                            <span className="check-row">
                              <input
                                type="checkbox"
                                checked={value === 'Подтверждаю'}
                                onChange={(e) => {
                                  setSaved(false);
                                  setValues({
                                    ...values,
                                    [r.field_code]: e.target.checked ? 'Подтверждаю' : '',
                                  });
                                }}
                              />
                              Подтверждаю корректность анкеты
                            </span>
                          ) : (
                            <Input
                              value={value}
                              readOnly={readOnly}
                              required
                              aria-label={r.field_label}
                              onChange={(e) => {
                                setSaved(false);
                                setValues({ ...values, [r.field_code]: e.target.value });
                              }}
                            />
                          )}
                          {r.format_rule && <span className="muted small">{r.format_rule}</span>}
                          {(app.sources[r.field_code]?.trim() ||
                            (value.trim() && r.target_db_field.startsWith('companies.'))) && (
                            <SourceBadge>{sourceLabel(app.sources[r.field_code])}</SourceBadge>
                          )}
                        </label>
                      );
                    })}
                  {index === 0 && app.product !== 'R01' && (
                    <>
                      <label className="form-field">
                        Срок транша
                        <Input
                          type="number"
                          min={1}
                          value={tranche}
                          required
                          onChange={(e) => setTranche(e.target.value)}
                        />
                      </label>
                      <label className="form-field">
                        Единица срока транша
                        <select value={unit} required onChange={(e) => setUnit(e.target.value)}>
                          <option value="">Выберите</option>
                          <option value="DAYS">Дни</option>
                          <option value="MONTHS">Месяцы</option>
                        </select>
                      </label>
                    </>
                  )}

                  {index === 3 &&
                    consentLabels.map(([key, label]) => (
                      <label className="check-row" key={key}>
                        <input
                          type="checkbox"
                          checked={consents[key]}
                          onChange={(event) => {
                            setSaved(false);
                            setConsents((old) => ({ ...old, [key]: event.target.checked }));
                          }}
                        />
                        {label}
                      </label>
                    ))}
                </fieldset>
              ))}
              {step === 4 && (
                <div>
                  <p>Проверьте данные перед отправкой. Решение по заявке принимает банк.</p>
                  <dl className="details">
                    <div>
                      <dt>Продукт</dt>
                      <dd>{products[app.product]}</dd>
                    </div>
                    <div>
                      <dt>Запрошенная сумма</dt>
                      <dd>{draftAmount(amount)}</dd>
                    </div>
                    <div>
                      <dt>Срок</dt>
                      <dd>
                        {term == null || !String(term).trim() ? 'Срок не указан' : `${term} мес.`}
                      </dd>
                    </div>
                    <div>
                      <dt>Цель</dt>
                      <dd>{purpose?.trim() || 'Не указана'}</dd>
                    </div>
                  </dl>
                  {missing.length ? (
                    <>
                      <h3>Осталось заполнить</h3>
                      <ul>
                        {missing.map((item) => (
                          <li key={item.key}>{item.label}</li>
                        ))}
                      </ul>
                    </>
                  ) : (
                    <p role="status">Все обязательные сведения заполнены.</p>
                  )}
                </div>
              )}
              <ErrorState message={action.error} onRetry={action.retry} />
              {saved && <p role="status">Черновик сохранён.</p>}
              <div className="actions http-form-actions">
                {step > 0 && (
                  <Action
                    type="button"
                    tone="ghost"
                    disabled={action.busy}
                    onClick={() => goStep(step - 1)}
                  >
                    Назад
                  </Action>
                )}
                <Action
                  type="button"
                  tone="outline"
                  disabled={action.busy}
                  onClick={() => void action.run(() => save())}
                >
                  Сохранить черновик
                </Action>
                {step < 4 ? (
                  <Action
                    type="button"
                    disabled={action.busy || !canVisit(step + 1)}
                    onClick={() => goStep(step + 1)}
                  >
                    Дальше: {formStepTitles[step + 1]}
                  </Action>
                ) : (
                  <Action type="submit" disabled={action.busy || missing.length > 0}>
                    {action.busy ? 'Сохраняем и проверяем…' : 'Отправить заявку'}
                  </Action>
                )}
                <Action
                  type="button"
                  tone="outline"
                  disabled={action.busy}
                  onClick={() =>
                    void action.run(async () => {
                      await save();
                      nav(`/client/applications/${app.id}`);
                    })
                  }
                >
                  Сохранить и обсудить с ассистентом
                </Action>
              </div>
            </Card>
          </form>
          {children}
        </div>
        <aside className="summary dark" aria-label="Сводка заявки">
          <p>{products[app.product]}</p>
          <h2 className="summary-amount">{draftAmount(amount)}</h2>
          <p>{term == null || !String(term).trim() ? 'Срок не указан' : `${term} мес.`}</p>
          <p>{purpose?.trim() || 'Цель не указана'}</p>
          <div className="spread">
            <span>Готовность заявки</span>
            <strong>{completeness}%</strong>
          </div>
          <progress aria-label="Готовность заявки" max={100} value={completeness} />
          {missing.length ? (
            <>
              <p className="small">Осталось заполнить:</p>
              <ul>
                {missing.slice(0, 5).map((item) => (
                  <li key={item.key}>{item.label}</li>
                ))}
              </ul>
              {missing.length > 5 && <p className="small">Ещё {missing.length - 5}</p>}
            </>
          ) : (
            <p>Все обязательные сведения заполнены.</p>
          )}
        </aside>
      </div>
    </div>
  );
}
