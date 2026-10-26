import { money } from '../domain/finance';
import { products, type Product } from '../domain/types';

/** The same server catalog terms in the products page and assistant. */
export function ProductTerms({ row }: { row: Record<string, unknown> }) {
  return (
    <>
      <h3>{products[row.product_code as Product]}</h3>
      <p className="muted">
        {row.min_amount == null ? '' : `От ${money(Number(row.min_amount))}`}{' '}
        {row.max_amount == null ? '' : `до ${money(Number(row.max_amount))}`}
      </p>
      <p>
        {row.min_contract_term_value == null
          ? ''
          : `Срок: ${row.min_contract_term_value}–${row.max_contract_term_value} ${row.contract_term_unit === 'MONTHS' ? 'мес.' : 'дней'}`}
      </p>
    </>
  );
}
