export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  });
  if (!response.ok) {
    let message = `The request could not be completed (${response.status}).`;
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === 'string') message = body.detail;
    } catch {
      /* Preserve the useful HTTP status when the response is not JSON. */
    }
    throw new Error(message);
  }
  return response.json() as Promise<T>;
}

export const number = (value: number | null | undefined, digits = 0) =>
  value == null || !Number.isFinite(value)
    ? '—'
    : new Intl.NumberFormat('en-GB', {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(value);
export const percent = (value: number | null | undefined, digits = 1) =>
  value == null ? '—' : `${number(value, digits)}%`;
export const month = (value: string, format: 'short' | 'long' = 'short') => {
  if (!value) return '—';
  const date = new Date(`${value.slice(0, 10)}T12:00:00Z`);
  return Number.isNaN(date.getTime())
    ? value
    : date.toLocaleDateString('en-GB', { month: format, year: 'numeric', timeZone: 'UTC' });
};
export const modelName = (value = '') =>
  ({
    persistence: 'Last observed',
    seasonal: 'Same month last year',
    seasonal_naive: 'Same month last year',
    seasonal_12: 'Same month last year',
    trailing_mean: 'Trailing average',
    trailing_average: 'Trailing average',
    moving_average: 'Trailing average',
    ridge: 'Regularized regression',
    lightgbm: 'LightGBM',
  })[value] ?? value.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase());
