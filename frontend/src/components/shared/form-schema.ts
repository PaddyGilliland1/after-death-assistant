/*
  Zod primitives and option helpers for EntityForm. Kept in a plain .ts
  file so entity-form.tsx only exports components (fast refresh friendly).

  Each helper pairs with an EntityForm field kind:
  - zText / zOptionalText        -> kind "text" or "textarea"
  - zMoney / zOptionalMoney      -> kind "money" (pounds, kept as a string)
  - zDate / zOptionalDate        -> kind "date" (ISO YYYY-MM-DD)
  - zEnumField                   -> kind "select"
  - zCheckbox                    -> kind "checkbox"
*/

import { z } from "zod"

/** Required free text. */
export const zText = (message = "This field is required") =>
  z.string().trim().min(1, message)

/** Optional free text. Empty input stays an empty string. */
export const zOptionalText = () => z.string().trim()

const MONEY_PATTERN = /^\d{1,12}(\.\d{1,2})?$/
const MONEY_MESSAGE = "Enter an amount in pounds, for example 1250 or 1250.50"

/** Required money amount in pounds, kept as a string for the API. */
export const zMoney = () =>
  z.string().trim().regex(MONEY_PATTERN, MONEY_MESSAGE)

/** Optional money amount. Empty input stays an empty string. */
export const zOptionalMoney = () =>
  z
    .string()
    .trim()
    .refine((value) => value === "" || MONEY_PATTERN.test(value), MONEY_MESSAGE)

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/

/** Required ISO date (the native date input produces YYYY-MM-DD). */
export const zDate = (message = "Enter a date") =>
  z.string().regex(DATE_PATTERN, message)

/** Optional ISO date. Empty input stays an empty string. */
export const zOptionalDate = () =>
  z
    .string()
    .refine((value) => value === "" || DATE_PATTERN.test(value), "Enter a date")

/** Required choice from a fixed set of values, e.g. a backend enum. */
export const zEnumField = <const T extends readonly [string, ...string[]]>(
  values: T,
  message = "Choose an option",
) => z.enum(values, { error: message })

/** Checkbox value. */
export const zCheckbox = () => z.boolean()

export interface SelectOption {
  value: string
  label: string
}

/** Builds select options from enum values, humanising snake_case labels. */
export function optionsFromEnum(
  values: readonly string[],
  labels?: Record<string, string>,
): SelectOption[] {
  return values.map((value) => {
    const words = value.replaceAll("_", " ")
    return {
      value,
      label: labels?.[value] ?? words.charAt(0).toUpperCase() + words.slice(1),
    }
  })
}
