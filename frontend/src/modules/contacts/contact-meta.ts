/*
  Contact module constants, form schema and payload mapping. Field names
  mirror backend/app/schemas/people.py (ContactCreate/ContactUpdate), which
  remains authoritative.
*/

import { z } from "zod"

import {
  optionsFromEnum,
  zCheckbox,
  zEnumField,
  zOptionalText,
  zText,
  type SelectOption,
} from "@/components/shared/form-schema"
import type { Contact, ContactCategory } from "@/lib/types"

/** Full backend ContactCategory enum, in display order. */
export const CONTACT_CATEGORIES = [
  "bank",
  "nsandi",
  "insurer",
  "pension",
  "utility",
  "telecom",
  "tv_licensing",
  "streaming",
  "council",
  "hmrc",
  "probate_registry",
  "solicitor",
  "accountant",
  "valuer",
  "registrar",
  "gp",
  "dentist",
  "optician",
  "employer",
  "landlord",
  "care_agency",
  "beneficiary",
  "gift_recipient",
  "creditor",
  "debtor",
  "executor",
  "membership",
  "other",
] as const satisfies readonly ContactCategory[]

const CATEGORY_LABEL_OVERRIDES: Record<string, string> = {
  nsandi: "NS&I",
  hmrc: "HMRC",
  tv_licensing: "TV Licensing",
  gp: "GP",
}

export const categoryOptions: SelectOption[] = optionsFromEnum(
  CONTACT_CATEGORIES,
  CATEGORY_LABEL_OVERRIDES,
)

/** Human readable label for a contact category. */
export function categoryLabel(category: string): string {
  return (
    categoryOptions.find((option) => option.value === category)?.label ??
    category
  )
}

export const notifiedMethodOptions: SelectOption[] = [
  { value: "letter", label: "Letter" },
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
  { value: "online", label: "Online form" },
  { value: "in_person", label: "In person" },
]

export const interactionChannelOptions: SelectOption[] = [
  { value: "phone", label: "Phone" },
  { value: "email", label: "Email" },
  { value: "letter", label: "Letter" },
  { value: "online", label: "Online" },
  { value: "in_person", label: "In person" },
]

export const interactionDirectionOptions: SelectOption[] = [
  { value: "outbound", label: "Outbound" },
  { value: "inbound", label: "Inbound" },
]

/**
 * True when the contact still needs notifying: notify_required with a
 * pending (or not yet set) notification status.
 */
export function needsNotifying(contact: Contact): boolean {
  return (
    contact.notify_required &&
    (contact.notification_status ?? "pending") === "pending"
  )
}

/* ----------------------------------------------------------------- form */

export const contactFormSchema = z.object({
  name: zText("Enter the contact's name"),
  category: zEnumField(CONTACT_CATEGORIES),
  org: zOptionalText(),
  relationship: zOptionalText(),
  email: zOptionalText(),
  phone: zOptionalText(),
  address: zOptionalText(),
  references: zOptionalText(),
  holds_or_handles: zOptionalText(),
  notify_required: zCheckbox(),
})

export type ContactFormValues = z.infer<typeof contactFormSchema>

/** Default form values, from an existing contact when editing. */
export function contactFormDefaults(
  contact?: Contact,
): ContactFormValues {
  return {
    name: contact?.name ?? "",
    category: contact?.category ?? ("" as ContactCategory),
    org: contact?.org ?? "",
    relationship: contact?.relationship ?? "",
    email: contact?.email ?? "",
    phone: contact?.phone ?? "",
    address: contact?.address ?? "",
    references: contact?.references?.join(", ") ?? "",
    holds_or_handles: contact?.holds_or_handles ?? "",
    notify_required: contact?.notify_required ?? false,
  }
}

/** Maps validated form values to the ContactCreate/ContactUpdate shape. */
export function toContactPayload(values: ContactFormValues) {
  return {
    name: values.name,
    category: values.category,
    org: values.org || null,
    relationship: values.relationship || null,
    email: values.email || null,
    phone: values.phone || null,
    address: values.address || null,
    references: values.references
      .split(",")
      .map((reference) => reference.trim())
      .filter(Boolean),
    holds_or_handles: values.holds_or_handles || null,
    notify_required: values.notify_required,
  }
}

/* -------------------------------------------------------- interactions */

/** Shape of GET /contacts/{id}/interactions rows (people.py). */
export interface ContactInteraction {
  id: string
  estate_id: string
  contact_id: string
  date: string
  channel: string | null
  direction: string | null
  summary: string | null
  follow_up_date: string | null
  by_user: string
  executor_private: boolean
  created_at: string
  updated_at: string
  created_by: string
}

export const interactionsKey = (contactId: string) =>
  ["/contacts", "interactions", contactId] as const

/** Newest first: by date, then by creation time. */
export function sortInteractionsNewestFirst(
  interactions: ContactInteraction[],
): ContactInteraction[] {
  return [...interactions].sort(
    (a, b) =>
      b.date.localeCompare(a.date) || b.created_at.localeCompare(a.created_at),
  )
}

/** Today's date as ISO YYYY-MM-DD for date input defaults. */
export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}
