import { describe, it, expect } from 'vitest';
import { payment, coverage, schedule } from '../domain/finance';
import { fields } from '../domain/fields';
import { applicableFields, validateField } from '../domain/forms';
import { assertTransition } from '../domain/status';
describe('Credit calculations', () => {
  it('matches V2 examples without hardcoded payments', () => {
    expect(Math.round(payment(1500000, 12))).toBe(142494);
    expect(Math.round(payment(1500000, 18))).toBe(100714);
    expect(Math.round(payment(1500000, 24))).toBe(79982);
    expect(coverage(330000, 60000, 3000000, 18)).toBeCloseTo(1.26, 2);
    expect(coverage(330000, 60000, 2200000, 18)).toBeCloseTo(1.59, 2);
  });
  it('amortizes the entire principal', () => {
    const rows = schedule(1500000, 12, Date.UTC(2026, 9, 24));
    expect(rows.at(-1)!.balance).toBeCloseTo(0, 6);
    expect(rows.reduce((s, r) => s + r.principal, 0)).toBeCloseTo(1500000, 6);
    expect(rows[0].balance).toBeCloseTo(1388631.49, 0);
  });
  it('handles zero interest and rejects invalid inputs', () => {
    expect(payment(1200, 12, 0)).toBe(100);
    for (const args of [
      [-1, 12],
      [100, 0],
      [NaN, 12],
      [100, 2.5],
    ])
      expect(() => payment(args[0], args[1])).toThrow();
  });
});
describe('Domain boundaries', () => {
  it('imports all 99 fields and filters applicant requirements', () => {
    expect(fields).toHaveLength(99);
    expect(applicableFields('R01', 'IP').some((f) => f.number === 11)).toBe(false);
    expect(applicableFields('R01', 'OOO').some((f) => f.number === 11)).toBe(true);
    expect(applicableFields('R03', 'IP').find((f) => f.number === 32)?.dbField).toBeTruthy();
  });
  it('validates identifiers and product-specific fields', () => {
    expect(
      validateField(
        fields.find((f) => f.code === 'R01_03')!,
        '123',
        'IP',
      ),
    ).toBe('Введите 12 цифр');
    expect(
      validateField(
        fields.find((f) => f.code === 'R03_32')!,
        '123',
        'IP',
      ),
    ).toBe('Введите 20 цифр');
    expect(
      validateField(
        fields.find((f) => f.code === 'R03_34')!,
        '044525593',
        'IP',
      ),
    ).toBeUndefined();
  });
  it('rejects signing before accepting and preserves request/review states', () => {
    expect(() => assertTransition('OFFERED', 'SIGNED_DEMO')).toThrow();
    expect(() => assertTransition('NEEDS_INFO', 'CHECKING')).not.toThrow();
    expect(() => assertTransition('MANUAL_REVIEW', 'NEEDS_INFO')).not.toThrow();
  });
});
