/** Monetary labels come from the bot; pair settlement/quote is a fallback for historical rows. */
export function normalizeCurrency(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const unit = value.trim().toUpperCase();
  return /^[A-Z0-9][A-Z0-9._-]{0,24}$/.test(unit) ? unit : null;
}
export function currencyFromPair(pair: unknown): string | null {
  if (typeof pair !== 'string' || !pair.includes('/')) return null;
  return normalizeCurrency(
    pair
      .slice(pair.indexOf('/') + 1)
      .split(':')
      .at(-1),
  );
}
export function commonCurrency(values: readonly unknown[]): string | null {
  if (!values.length) return null;
  const units = values.map(normalizeCurrency);
  if (units.some((v) => !v)) return null;
  return new Set(units).size === 1 ? units[0]! : null;
}
export function requireCommonCurrency(values: readonly unknown[]): void {
  if (values.length && !commonCurrency(values))
    throw new Error(
      'Không thể cộng số liệu khi đơn vị tiền khác nhau hoặc chưa rõ. Chọn một bot hoặc nhóm dùng cùng loại tiền.',
    );
}
