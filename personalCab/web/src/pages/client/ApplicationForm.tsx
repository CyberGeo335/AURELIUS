import { useState, useRef } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { Check, ArrowLeft } from 'lucide-react';
import { Input } from '../../components/ui/input';
import { useApi, useCredit, useSession, useAction } from '../../app/context';
import {
  Action,
  Card,
  ErrorState,
  MonthlyBars,
  SourceBadge,
  KeyValue,
  EmptyState,
} from '../../components/v2/primitives';
import { applicableFields, validateApplication, validateField } from '../../domain/forms';
import { money, payment, decimal } from '../../domain/finance';
import { products, type Scenario } from '../../domain/types';
import { purposeOptions } from '../../domain/products';
import { Disclosure } from '../../components/v2/Disclosure';
import { ApplicationFields } from '../../components/v2/primitives';
import { parseStatement, statementPeriods } from '../../domain/statement';
import type { DraftPatch } from '../../api/CreditApi';
export function ApplicationForm() {
  const { id } = useParams();
  const api = useApi();
  const state = useCredit();
  const { session } = useSession();
  const nav = useNavigate();
  const a = state.applications.find((a) => a.id === id && a.companyId === session!.profile);
  const action = useAction();
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<string[]>([]);
  const [manualMonths, setManualMonths] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);
  if (!a)
    return (
      <EmptyState
        title={
          state.applications.some((app) => app.id === id) ? 'Нет доступа' : 'Заявка не найдена'
        }
      >
        <Link to="/client/applications">К списку заявок</Link>
      </EmptyState>
    );
  if (a.status !== 'DRAFT')
    return (
      <EmptyState title="Заявка уже отправлена">
        <Link to={`/client/applications/${a.id}`}>Перейти к проверке</Link>
      </EmptyState>
    );
  const company = state.companies.find((c) => c.id === a.companyId)!;
  const definitions = applicableFields(a.product, company.entity);
  const steps = ['Цель и сумма', 'Бизнес и обороты', 'Согласия', 'Отправка'];
  const allErrors = validateApplication(a, company);
  const missing = Object.entries(allErrors).map(([key, message]) => ({
    key,
    message,
    label: definitions.find((f) => f.code === key)?.label ?? message,
  }));
  const completeness = Math.round((1 - missing.length / (definitions.length + 6)) * 100);
  const monthly = a.monthly ?? company.monthly;
  const save = (patch: DraftPatch) => {
    void action.run(() => api.saveDraft(a.id, patch));
  };
  const setField = (code: string, value: string) => {
    const n = Number(code.split('_')[1]);
    const patch: DraftPatch = { fields: { ...a.fields, [code]: value } };
    if (n === 5) patch.amount = Number(value);
    if (n === 6) patch.term = Number(value);
    if (n === 4) patch.purpose = value;
    save(patch);
    const definition = definitions.find((f) => f.code === code);
    setErrors((old) => ({
      ...old,
      [code]: definition
        ? (validateField(definition, value, company.entity, value === company.inn) ?? '')
        : '',
    }));
  };
  const showErrors = (errs: Record<string, string>) => {
    setErrors(errs);
    setTimeout(() => errorRef.current?.focus(), 0);
  };
  const next = () => {
    const all = validateApplication(a, company);
    const current = Object.fromEntries(
      Object.entries(all).filter(([key]) => {
        const n = Number(key.split('_')[1]);
        return a.step === 0
          ? n <= 8 || n >= 32
          : a.step === 1
            ? (n >= 9 && n <= 30) ||
              ['business', 'statement', 'leasing', 'flow', 'existing'].includes(key)
            : ['consentBki', 'consentData'].includes(key);
      }),
    );
    if (Object.keys(current).length) showErrors(current);
    else {
      setErrors({});
      save({ step: a.step + 1 });
      window.scrollTo(0, 0);
    }
  };
  const renderFields = (numbers: (n: number) => boolean) =>
    definitions
      .filter((f) => numbers(f.number))
      .map((f) => {
        const locked = [1, 2, 7].includes(f.number) || (f.product === 'R02' && f.number === 34);
        const auto = locked || /Авто|система|Выделить/.test(f.method);
        const editable = !auto || editing.includes(f.code);
        const value = a.fields[f.code] ?? '';
        return (
          <div className={`form-field ${auto ? 'autofill' : ''}`} key={f.code}>
            <label htmlFor={f.code}>
              {f.label}
              <span className="required" aria-hidden>
                {' '}
                *
              </span>
            </label>
            {f.number === 4 ? (
              <>
                <select
                  id={f.code}
                  value={value}
                  onChange={(e) => setField(f.code, e.target.value)}
                >
                  {!purposeOptions.includes(value) && <option>{value}</option>}
                  {purposeOptions.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
                <label className="small muted">
                  Уточнение цели, если нужно
                  <Input
                    value={a.fields[`${a.product}_purpose_note`] ?? ''}
                    onChange={(e) => setField(`${a.product}_purpose_note`, e.target.value)}
                  />
                </label>
              </>
            ) : editable ? (
              <Input
                id={f.code}
                value={value}
                aria-invalid={!!errors[f.code]}
                aria-describedby={errors[f.code] ? `${f.code}-error` : undefined}
                onBlur={() => {
                  const e = validateField(f, value, company.entity, value === company.inn);
                  if (e) setErrors((v) => ({ ...v, [f.code]: e }));
                }}
                onChange={(e) => setField(f.code, e.target.value)}
                type={
                  [5, 6].includes(f.number) || (a.product === 'R02' && [32, 33].includes(f.number))
                    ? 'number'
                    : [15, 23].includes(f.number)
                      ? 'date'
                      : 'text'
                }
              />
            ) : (
              <div className="autofill-value">
                <output id={f.code}>{value}</output>
                {!locked && (
                  <button
                    className="text-button"
                    type="button"
                    onClick={() => {
                      setEditing((e) => [...e, f.code]);
                      save({ sources: { ...a.sources, [f.code]: 'Клиент · исправлено' } });
                    }}
                  >
                    Исправить
                  </button>
                )}
              </div>
            )}
            <div className="field-hint">
              <SourceBadge>{a.sources[f.code] ?? f.source}</SourceBadge>
              {auto && (
                <span className="small muted">
                  Снимок от {new Date(a.sourceDate ?? a.created).toLocaleDateString('ru-RU')}
                </span>
              )}
              {f.number === 3 && value === company.inn && (
                <span className="small muted">
                  Синтетический ИНН из демо-данных. Не используется для реальных запросов.
                </span>
              )}
            </div>
            {errors[f.code] && (
              <p className="field-error" id={`${f.code}-error`}>
                {errors[f.code]}
              </p>
            )}
          </div>
        );
      });
  return (
    <div className="form-layout">
      <aside className="vertical-steps" aria-label="Шаги анкеты">
        <span className="draft-saved">
          <Check aria-hidden size={14} />
          Черновик сохранён
        </span>
        {steps.map((name, i) => (
          <button
            key={name}
            disabled={i > (a.furthestStep ?? a.step)}
            aria-current={a.step === i ? 'step' : undefined}
            onClick={() => save({ step: i })}
          >
            <span>{i < a.step ? <Check aria-hidden size={18} /> : i + 1}</span>
            {name}
          </button>
        ))}
        <Link to="/client/applications" className="muted small">
          Выйти из заявки
        </Link>
      </aside>
      <div className="form-content">
        <div ref={errorRef} tabIndex={-1}>
          {Object.values(errors).some(Boolean) && (
            <div className="error-box" role="alert">
              <div>
                <strong>Проверьте обязательные поля</strong>
                <ul>
                  {Object.entries(errors)
                    .filter(([, v]) => v)
                    .map(([k, v]) => (
                      <li key={k}>
                        <a href={`#${k}`}>
                          {definitions.find((f) => f.code === k)?.label ?? k}: {v}
                        </a>
                      </li>
                    ))}
                </ul>
              </div>
            </div>
          )}
        </div>
        <ErrorState message={action.error} onRetry={action.retry} />
        {a.step === 0 && (
          <Card>
            <p className="eyebrow">Новая заявка · {a.product}</p>
            <h1>На что нужны деньги?</h1>
            <p className="muted">
              Укажите цель, сумму и срок. Условия можно будет пересмотреть до принятия предложения.
            </p>
            <div className="form-fields">{renderFields((n) => n <= 8 || n >= 32)}</div>
            <label className="form-field">
              Демо-сценарий
              <select
                value={a.scenario}
                onChange={(e) => save({ scenario: e.target.value as Scenario })}
              >
                <option value="normal">Обычная проверка</option>
                <option value="missing">Не хватает выписки</option>
                <option value="external">Внешний источник недоступен</option>
                <option value="decline">Отказ: действующая просрочка</option>
              </select>
            </label>
          </Card>
        )}
        {a.step === 1 && (
          <>
            <Card>
              <h1>Это ваш бизнес?</h1>
              <p className="muted">
                Реквизиты из демонстрационного снимка {company.entity === 'IP' ? 'ЕГРИП' : 'ЕГРЮЛ'}{' '}
                по ИНН {a.fields[`${a.product}_03`]}. Проверьте каждое значение.
              </p>
              <div className="form-fields two-columns">
                {renderFields((n) => (n >= 9 && n <= 17) || n === 22)}
              </div>
              <details
                open={
                  definitions.some((f) => f.number >= 18 && f.number <= 30 && errors[f.code]) ||
                  undefined
                }
              >
                <summary>Деятельность, контакты и полномочия</summary>
                <p className="small muted">
                  Заполнили демонстрационными данными профиля. Проверьте и при необходимости
                  исправьте.
                </p>
                <div className="form-fields two-columns">
                  {renderFields((n) => n >= 18 && n <= 30 && n !== 22)}
                </div>
              </details>
              <Action
                id="business"
                tone={a.businessConfirmed ? 'soft' : 'ink'}
                onClick={() => save({ businessConfirmed: !a.businessConfirmed })}
              >
                {a.businessConfirmed ? (
                  <>
                    <Check aria-hidden size={18} /> Данные подтверждены
                  </>
                ) : (
                  'Всё верно'
                )}
              </Action>
            </Card>
            <Card>
              <h1>Сколько зарабатывает бизнес?</h1>
              <p className="muted">Обороты за 12 месяцев помогают оценить нагрузку на бизнес.</p>
              <div className="actions">
                <Action
                  id="statement"
                  tone={a.statement ? 'ink' : 'soft'}
                  onClick={() => {
                    setManualMonths(false);
                    save({
                      statement: true,
                      monthly: company.monthly,
                      statementMonths: statementPeriods,
                    });
                  }}
                >
                  {a.statement && <Check aria-hidden size={18} />} Взять демо-выписку
                </Action>
                <Action
                  tone={manualMonths ? 'ink' : 'soft'}
                  onClick={() => setManualMonths(!manualMonths)}
                >
                  Ввести вручную
                </Action>
                <label className="file-button">
                  Загрузить PDF / CSV
                  <input
                    type="file"
                    accept=".pdf,.csv"
                    onChange={async (e) => {
                      const f = e.target.files?.[0];
                      if (f) {
                        if (!/\.(pdf|csv)$/i.test(f.name) || f.size > 10 * 1024 * 1024) {
                          action.setError('Нужен PDF или CSV до 10 МБ.');
                          return;
                        }
                        if (f.name.toLowerCase().endsWith('.csv')) {
                          try {
                            const data = parseStatement(await f.text());
                            const updated = [...(a.monthly ?? Array(12).fill(0))];
                            for (const [period, amount] of Object.entries(data))
                              updated[statementPeriods.indexOf(period)] = amount / 1000000;
                            save({
                              statement: true,
                              monthly: updated,
                              statementMonths: [
                                ...new Set([...(a.statementMonths ?? []), ...Object.keys(data)]),
                              ],
                              files: [...a.files, f.name],
                            });
                            action.setError('');
                          } catch (error) {
                            action.setError(
                              error instanceof Error ? error.message : 'Не удалось прочитать CSV.',
                            );
                          }
                        } else save({ statement: true, files: [...a.files, f.name] });
                      }
                    }}
                  />
                </label>
              </div>
              <p className="small muted">
                Файл остаётся на устройстве; для демо сохраняется имя. Реального анализа выписки
                нет.
              </p>
              {a.files.length > 0 && <p className="small">{a.files.join(', ')}</p>}
              {a.statementMonths && a.statementMonths.length < 12 && (
                <div role="alert" className="error-box">
                  Не хватает {12 - a.statementMonths.length} месяцев. Дозагрузите CSV с недостающими
                  периодами.
                </div>
              )}
              {a.statementMonths && (
                <div className="coverage-months" aria-label="Покрытие выписки">
                  {statementPeriods.map((period) => (
                    <span
                      key={period}
                      className={a.statementMonths!.includes(period) ? 'complete' : 'missing'}
                      title={period}
                    >
                      {period.slice(5)}
                    </span>
                  ))}
                </div>
              )}
              {manualMonths && (
                <div className="manual-months">
                  <p className="small muted">
                    Демонстрационные поступления, ₽. Проверьте каждый месяц.
                  </p>
                  <div className="month-inputs">
                    {statementPeriods.map((period, i) => (
                      <label className="form-field" key={period}>
                        {period}
                        <Input
                          type="number"
                          min={0}
                          value={Math.round(monthly[i] * 1000000)}
                          onChange={(e) => {
                            const values = [...monthly];
                            values[i] = Number(e.target.value) / 1000000;
                            save({
                              monthly: values,
                              statement: true,
                              statementMonths: statementPeriods,
                            });
                          }}
                        />
                      </label>
                    ))}
                  </div>
                  <Action
                    tone="soft"
                    onClick={() =>
                      save({ monthly, statement: true, statementMonths: statementPeriods })
                    }
                  >
                    Подтвердить обороты
                  </Action>
                </div>
              )}
              <div className="metrics">
                <KeyValue
                  label="За 12 месяцев"
                  value={money(monthly.reduce((s, v) => s + v, 0) * 1000000)}
                />
                <KeyValue
                  label="В среднем в месяц"
                  value={`${decimal(monthly.reduce((s, v) => s + v, 0) / 12)} млн ₽`}
                />
              </div>
              <MonthlyBars values={monthly} />
              <div className="form-fields two-columns">
                <label className="form-field" htmlFor="flow">
                  Свободный поток в месяц, ₽
                  <Input
                    id="flow"
                    type="number"
                    value={a.flow}
                    onChange={(e) => save({ flow: Number(e.target.value) })}
                  />
                </label>
                <label className="form-field" htmlFor="existing">
                  Действующие платежи, ₽
                  <Input
                    id="existing"
                    type="number"
                    value={a.existing}
                    onChange={(e) => save({ existing: Number(e.target.value) })}
                  />
                </label>
              </div>
              <div className="dark inset" id="leasing">
                <h3>Регулярный платёж {money(company.existing)}</h3>
                <p className="muted">
                  {company.entity === 'IP'
                    ? 'Это действующий лизинг? Учтём его в нагрузке.'
                    : 'Подтвердите действующий кредит.'}
                </p>
                <div className="actions">
                  <Action
                    tone={a.leasing === true ? 'white' : 'red'}
                    onClick={() => save({ leasing: true, existing: company.existing })}
                  >
                    {a.leasing === true
                      ? 'Подтверждено'
                      : company.entity === 'IP'
                        ? 'Да, это лизинг'
                        : 'Подтвердить кредит'}
                  </Action>
                  <Action tone="outline" onClick={() => save({ leasing: false, existing: 0 })}>
                    {a.leasing === false ? 'Нет, учтено' : 'Нет, другое'}
                  </Action>
                </div>
              </div>
            </Card>
          </>
        )}
        {a.step === 2 && (
          <Card>
            <h1>Согласия и проверка</h1>
            <p className="muted">
              Каждое согласие подтверждается отдельно. Сообщение помощнику его не заменяет.
            </p>
            <label className="check-row" id="consentBki">
              <input
                type="checkbox"
                checked={a.consentBki}
                onChange={(e) => save({ consentBki: e.target.checked })}
              />
              <span>
                <strong>Разрешаю запросить кредитную историю в БКИ</strong>
                <p className="small muted">
                  Для рассмотрения этой заявки. Версия bki-demo-2026.10-v1. Демонстрационное
                  согласие, реальный запрос не выполняется.
                </p>
              </span>
            </label>
            <label className="check-row" id="consentData">
              <input
                type="checkbox"
                checked={a.consentData}
                onChange={(e) => save({ consentData: e.target.checked })}
              />
              <span>
                Согласен на обработку данных заявки на демо-стенде. Версия data-demo-2026.10-v1.
              </span>
            </label>
          </Card>
        )}
        {a.step === 3 && (
          <Card>
            <h1>Всё готово к отправке</h1>
            <p className="muted">Проверьте заявку. После отправки банк начнёт проверку данных.</p>
            <div className="form-fields two-columns">
              <KeyValue label="Компания" value={company.name} />
              <KeyValue label="Продукт" value={products[a.product]} />
              <KeyValue label="Сумма" value={money(a.amount)} />
              <KeyValue label="Срок" value={`${a.term} месяцев`} />
              <KeyValue label="Цель" value={a.purpose} />
              <KeyValue
                label="Согласие БКИ"
                value={a.consentBki ? 'Подтверждено отдельно' : 'Не получено'}
              />
              <KeyValue label="Подписант" value={a.fields[`${a.product}_29`]} />
              <KeyValue label="Основание полномочий" value={a.fields[`${a.product}_30`]} />
            </div>
            <Disclosure
              title="Проверить все данные анкеты"
              description="Реквизиты, деятельность, контакты и полномочия"
            >
              <ApplicationFields app={a} company={company} showCodes={false} />
            </Disclosure>
            <label className="check-row" id={`${a.product}_31`}>
              <input
                type="checkbox"
                checked={a.fields[`${a.product}_31`] === 'Подтверждаю'}
                onChange={(e) => setField(`${a.product}_31`, e.target.checked ? 'Подтверждаю' : '')}
              />
              <span>Подтверждаю корректность анкеты и полномочия на подачу заявки.</span>
            </label>
            <Action
              disabled={action.busy || missing.length > 0}
              onClick={() => {
                const errs = validateApplication(a, company);
                if (Object.keys(errs).length) {
                  showErrors(errs);
                  return;
                }
                void action.run(async () => {
                  await api.submit(a.id);
                  nav(`/client/applications/${a.id}`);
                });
              }}
            >
              {action.busy ? 'Отправляем…' : 'Отправить заявку'}
            </Action>
            {missing.length > 0 && (
              <p className="small field-error">
                Перед отправкой: {missing.map((m) => m.message).join('; ')}
              </p>
            )}
          </Card>
        )}
        <div className="spread">
          <Action
            tone="ghost"
            onClick={() => (a.step > 0 ? save({ step: a.step - 1 }) : nav('/client'))}
          >
            <ArrowLeft aria-hidden size={18} />
            Назад
          </Action>
          {a.step < 3 && <Action onClick={next}>Дальше: {steps[a.step + 1].toLowerCase()}</Action>}
        </div>
      </div>
      <aside className="summary dark">
        <p className="muted">{products[a.product]} без залога</p>
        <h2 className="summary-amount">{money(a.amount || 0)}</h2>
        <div className="chips">
          <SourceBadge>{a.term} месяцев</SourceBadge>
          <SourceBadge>{a.purpose}</SourceBadge>
        </div>
        <hr />
        <p className="muted">Примерный платёж</p>
        <h2>
          {Number.isFinite(a.amount) && a.amount > 0 && Number.isInteger(a.term) && a.term > 0
            ? money(payment(a.amount, a.term))
            : '—'}
        </h2>
        <p className="small muted">В месяц по демо-ставке 24,9%. Точные условия будут в решении.</p>
        <hr />
        <div className="spread">
          <span>Заявка готова</span>
          <strong>{completeness}%</strong>
        </div>
        <progress value={completeness} max={100} aria-label="Готовность заявки" />
        {missing.length > 0 && (
          <ul className="readiness-list">
            {missing.slice(0, 4).map((item) => (
              <li key={item.key}>{item.label}</li>
            ))}
          </ul>
        )}
        <p className="small muted">
          <Check aria-hidden size={14} /> Черновик сохраняется автоматически
        </p>
        <button className="text-button" onClick={() => save({ step: 0 })}>
          Изменить сумму или срок
        </button>
      </aside>
    </div>
  );
}
