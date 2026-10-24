// FTS INN structure and control digits; see REQUIREMENTS-AUDIT.md for sources.
export function validInn(value: string) {
  if (!/^(?:\d{10}|\d{12})$/.test(value) || /^0+$/.test(value)) return false;
  const d = [...value].map(Number);
  const control = (weights: number[]) =>
    (weights.reduce((sum, w, i) => sum + w * d[i], 0) % 11) % 10;
  return value.length === 10
    ? control([2, 4, 10, 3, 5, 9, 4, 6, 8]) === d[9]
    : control([7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === d[10] &&
        control([3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]) === d[11];
}
export const syntheticInns = new Set(['771234567890', '7701234567']);
