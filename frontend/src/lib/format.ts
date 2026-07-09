const gbp = new Intl.NumberFormat("en-GB", {
  style: "currency",
  currency: "GBP",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Formats a value in pounds for display, for example 12500 becomes £12,500.00 (pence always shown: accounting figures must not round). */
export function formatCurrency(value: number): string {
  return gbp.format(value)
}

const count = new Intl.NumberFormat("en-GB")

/** Formats a whole number with en-GB grouping. */
export function formatCount(value: number): string {
  return count.format(value)
}
