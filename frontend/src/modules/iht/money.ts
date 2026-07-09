/*
  Display helpers for the IHT workbench. Engine figures arrive as decimal
  strings (backend Decimal) and are shown exactly as returned: digits are
  grouped for reading but never rounded or recomputed. The shared
  formatMoney helper is deliberately not used here because it rounds to
  whole pounds, and tax figures must show their pence.
*/

/**
 * Formats a decimal money string exactly, for example "325000.00"
 * becomes "£325,000.00". Returns the fallback when the value is missing
 * or not a plain decimal.
 */
export function formatMoneyExact(
  value: string | number | null | undefined,
  fallback = "",
): string {
  if (value === null || value === undefined || value === "") return fallback
  const match = /^(-)?(\d+)(?:\.(\d+))?$/.exec(String(value).trim())
  if (!match) return fallback
  const [, sign, whole, fraction] = match
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",")
  return `${sign ? "-" : ""}£${grouped}${fraction ? `.${fraction}` : ""}`
}

const percentFormat = new Intl.NumberFormat("en-GB", {
  style: "percent",
  maximumFractionDigits: 2,
})

/**
 * Formats a decimal rate fraction such as "0.40" as "40%". This is a
 * display convention, not arithmetic on the engine's figure. Returns the
 * fallback when the value does not parse.
 */
export function formatRate(
  value: string | null | undefined,
  fallback = "",
): string {
  if (value === null || value === undefined || value === "") return fallback
  const numeric = Number(value)
  if (Number.isNaN(numeric)) return fallback
  return percentFormat.format(numeric)
}
