export function counted(n: number, forms: [string, string, string]) {
  const mod100 = Math.abs(n) % 100,
    mod10 = mod100 % 10;
  return `${n} ${forms[mod100 >= 11 && mod100 <= 14 ? 2 : mod10 === 1 ? 0 : mod10 >= 2 && mod10 <= 4 ? 1 : 2]}`;
}
