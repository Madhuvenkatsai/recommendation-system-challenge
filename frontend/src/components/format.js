export function formatNumber(value) {
  if (value === null || value === undefined) return '—'
  return new Intl.NumberFormat().format(value)
}

export function formatDate(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

export function percent(value, digits = 1) {
  return value === null || value === undefined
    ? '—'
    : `${(value * 100).toFixed(digits)}%`
}
