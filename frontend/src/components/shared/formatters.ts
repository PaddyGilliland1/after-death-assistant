/*
  Display helpers for values as they arrive from the API: money as strings
  (backend Decimal serialised to JSON), dates as ISO strings. Built on the
  shared GBP formatter in src/lib/format.ts.
*/

import { formatCurrency } from "@/lib/format"

const dateFormatter = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
})

/**
 * Formats a money value from the API for display, for example "12500.00"
 * becomes £12,500. Returns the fallback for null, undefined or anything
 * that does not parse as a number.
 */
export function formatMoney(
  value: string | number | null | undefined,
  fallback = "",
): string {
  if (value === null || value === undefined || value === "") return fallback
  const amount = typeof value === "number" ? value : Number(value)
  if (Number.isNaN(amount)) return fallback
  return formatCurrency(amount)
}

/**
 * Formats an ISO date or datetime string in en-GB style, for example
 * "2026-03-05" becomes 5 Mar 2026. Returns the fallback when the value is
 * missing or unparseable.
 */
export function formatDate(
  value: string | null | undefined,
  fallback = "",
): string {
  if (!value) return fallback
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return fallback
  return dateFormatter.format(parsed)
}

/** Turns a snake_case code such as "iht_payment" into "Iht payment". */
export function humaniseCode(value: string | null | undefined): string {
  if (!value) return ""
  const words = value.replaceAll("_", " ").trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}
