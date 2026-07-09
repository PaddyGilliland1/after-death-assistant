/*
  Payload helpers for register forms. EntityForm keeps optional inputs as
  empty strings; the API expects those fields to be omitted on create and
  nulled on update (PATCH applies only the fields present, so null is how
  a field is cleared).
*/

export type Payload = Record<string, unknown>

/** Drops empty-string and undefined values. Use for create payloads. */
export function omitEmpty(values: Payload): Payload {
  return Object.fromEntries(
    Object.entries(values).filter(
      ([, value]) => value !== "" && value !== undefined,
    ),
  )
}

/** Turns empty strings into null so a PATCH can clear a field. */
export function emptyToNull(values: Payload): Payload {
  return Object.fromEntries(
    Object.entries(values).map(([key, value]) => [
      key,
      value === "" ? null : value,
    ]),
  )
}
