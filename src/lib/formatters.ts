export function formatAudienceHeat(value: unknown) {
  if (value === null || value === undefined || value === '') return ''
  const raw = String(value).trim()
  if (!raw) return ''
  if (raw.includes('人在看')) return raw
  if (/[万亿]/.test(raw)) return `${raw.replace(/人?在看/g, '')}人在看`

  const numericText = raw.replace(/,/g, '').match(/\d+(?:\.\d+)?/)?.[0]
  const numeric = Number(numericText)
  if (!Number.isFinite(numeric)) return raw

  if (numeric >= 100_000_000) {
    return `${trimUnit(numeric / 100_000_000)}亿人在看`
  }
  if (numeric >= 10_000) {
    return `${trimUnit(numeric / 10_000)}万人在看`
  }
  return `${Math.round(numeric)}人在看`
}

function trimUnit(value: number) {
  return value.toFixed(value >= 100 ? 0 : value >= 10 ? 1 : 2).replace(/\.0+$/, '').replace(/(\.\d*[1-9])0+$/, '$1')
}
