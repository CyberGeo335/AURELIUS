import { BusinessProducts } from '../../business/BusinessPages';
import { useState } from 'react';
import { useNavigate } from 'react-router';
import {
  ArrowUpRight,
  MessageCircle,
  Repeat2,
  ShoppingBag,
  WalletCards,
  Calculator,
  Check,
} from 'lucide-react';
import { useApi, useSession, useAction } from '../../app/context';
import { Action, Card, ErrorState } from '../../components/v2/primitives';
import { Input } from '../../components/ui/input';
import { productInfo, recommendedProduct, type Need } from '../../domain/products';
import { products, type Product } from '../../domain/types';
import { payment, money } from '../../domain/finance';
function MockProducts({ onAssistant }: { onAssistant: (seed?: string) => void }) {
  const [need, setNeed] = useState<Need>('once');
  const [chosen, setChosen] = useState<Product>('R01');
  const [amount, setAmount] = useState(1500000);
  const [term, setTerm] = useState(12);
  const api = useApi();
  const { session } = useSession();
  const action = useAction();
  const nav = useNavigate();
  const recommended = recommendedProduct[need];
  const info = productInfo[chosen];
  const valid =
    Number.isFinite(amount) &&
    amount >= info.min &&
    amount <= info.max &&
    Number.isInteger(term) &&
    term >= info.minTerm &&
    term <= info.maxTerm;
  const needs: [Need, string, typeof ShoppingBag][] = [
    ['once', 'Разовая закупка', ShoppingBag],
    ['recurring', 'Закупки каждый месяц', Repeat2],
    ['gap', 'Не хватает до поступления выручки', WalletCards],
  ];
  return (
    <>
      <div className="page-title">
        <div>
          <p className="eyebrow">Финансирование бизнеса</p>
          <h1>Под вашу задачу</h1>
          <p className="muted">
            Выберите продукт сами или расскажите помощнику, на что нужны деньги.
          </p>
        </div>
      </div>
      <Card className="product-guide">
        <div>
          <span className="assistant-label">
            <MessageCircle aria-hidden size={17} />
            Помощник с выбором
          </span>
          <h2>
            Необязательно разбираться
            <br />в кредитах
          </h2>
          <p>Расскажите о задаче. Помощник предложит варианты и объяснит, чем они отличаются.</p>
          <Action className="assistant-action" onClick={() => onAssistant()}>
            Подобрать с помощником <ArrowUpRight aria-hidden size={18} />
          </Action>
        </div>
        <div className="need-picker">
          <p className="small">Или начните с цели</p>
          {needs.map(([key, label, Icon]) => (
            <button
              key={key}
              aria-pressed={need === key}
              onClick={() => {
                setNeed(key);
                setChosen(recommendedProduct[key]);
              }}
            >
              <Icon aria-hidden size={21} />
              {label}
              {need === key && <Check aria-hidden size={18} />}
            </button>
          ))}
          <p className="small">Подсказка по назначению продукта. Это не одобрение.</p>
        </div>
      </Card>
      <div className="product-cards" id="catalog">
        {[
          recommended,
          ...(['R01', 'R02', 'R03'] as Product[]).filter((p) => p !== recommended),
        ].map((code) => (
          <Card className={`product-option ${chosen === code ? 'selected' : ''}`} key={code}>
            <div className="spread">
              <span className="eyebrow">{code}</span>
              {code === recommended && (
                <span className="status status-OFFERED">Под вашу задачу</span>
              )}
            </div>
            <h2>{products[code]}</h2>
            <p className="muted">{productInfo[code].description}</p>
            <p className="product-terms">
              <strong>До 5 млн ₽</strong>
              <span>3–24 месяца · демо-условия</span>
            </p>
            <div className="product-reason">
              <Check aria-hidden size={17} />
              <p className="small">{productInfo[code].reason}</p>
            </div>
            <Action
              tone={chosen === code ? 'ink' : 'soft'}
              onClick={() => setChosen(code)}
              aria-pressed={chosen === code}
            >
              {chosen === code ? 'Выбран для расчёта' : 'Рассчитать условия'}
            </Action>
          </Card>
        ))}
      </div>
      <Card className="pre-calculator">
        <div>
          <span className="eyebrow">
            <Calculator aria-hidden size={18} /> Предварительный расчёт
          </span>
          <h2>{products[chosen]}</h2>
          <p className="muted">
            Оцените платёж до подачи заявки.
            <br />
            Индивидуальные условия банк предложит после проверки.
          </p>
          <div className="calculator-fields">
            <label className="form-field">
              Сумма, ₽
              <Input
                type="number"
                min={info.min}
                max={info.max}
                value={amount}
                onChange={(e) => setAmount(Number(e.target.value))}
              />
            </label>
            <label className="form-field">
              Срок, месяцев
              <Input
                type="number"
                min={info.minTerm}
                max={info.maxTerm}
                value={term}
                onChange={(e) => setTerm(Number(e.target.value))}
              />
            </label>
          </div>
          {!valid && (
            <p role="alert" className="field-error">
              Сумма от {money(info.min)} до {money(info.max)}, срок {info.minTerm}–{info.maxTerm}{' '}
              месяца.
            </p>
          )}
        </div>
        <div className="calculator-result">
          <p className="small muted">Примерный платёж в месяц</p>
          <strong>{valid ? `≈ ${money(payment(amount, term))}` : '—'}</strong>
          <p className="small muted">
            Предварительно · демо-ставка 24,9%
            {chosen !== 'R01' ? ' · пример полного использования лимита с аннуитетом' : ''}
          </p>
          <ErrorState message={action.error} onRetry={action.retry} />
          <Action
            disabled={!valid || action.busy}
            onClick={() =>
              action.run(async () => {
                const id = await api.createDraft(session!.profile, chosen);
                await api.saveDraft(id, { amount, term });
                nav(`/client/new/${id}`);
              })
            }
          >
            Оформить заявку <ArrowUpRight aria-hidden size={18} />
          </Action>
          <button
            className="text-button"
            onClick={() =>
              onAssistant(
                `Помоги выбрать продукт для задачи: ${needs.find((n) => n[0] === need)![1]}.`,
              )
            }
          >
            Обсудить с помощником
          </button>
        </div>
      </Card>
    </>
  );
}

export function Products(props: { onAssistant: (seed?: string) => void }) {
  return import.meta.env.VITE_API_MODE === 'http' ? (
    <BusinessProducts />
  ) : (
    <MockProducts {...props} />
  );
}
