/*
  Create and edit form for a contact, built on the shared EntityForm with
  the full backend category enum. The caller maps validated values to a
  payload with toContactPayload and performs the mutation.
*/

import {
  EntityForm,
  type EntityField,
} from "@/components/shared/entity-form"
import type { Contact } from "@/lib/types"

import {
  categoryOptions,
  contactFormDefaults,
  contactFormSchema,
  type ContactFormValues,
} from "./contact-meta"

const fields: EntityField<ContactFormValues>[] = [
  { name: "name", label: "Name", kind: "text", autoComplete: "off" },
  {
    name: "category",
    label: "Category",
    kind: "select",
    options: categoryOptions,
  },
  { name: "org", label: "Organisation", kind: "text", required: false },
  {
    name: "relationship",
    label: "Relationship to the deceased",
    kind: "text",
    required: false,
    placeholder: "For example: current account provider",
  },
  { name: "email", label: "Email", kind: "text", required: false },
  { name: "phone", label: "Phone", kind: "text", required: false },
  { name: "address", label: "Address", kind: "textarea", required: false },
  {
    name: "references",
    label: "References",
    kind: "text",
    required: false,
    description:
      "Account or policy references, separated by commas.",
  },
  {
    name: "holds_or_handles",
    label: "Holds or handles",
    kind: "text",
    required: false,
    placeholder: "For example: current account, house insurance",
  },
  {
    name: "notify_required",
    label: "Notification required",
    kind: "checkbox",
    description:
      "Tick when this organisation or person must be told of the death.",
  },
]

export interface ContactFormProps {
  /** When set, the form edits this contact; otherwise it creates one. */
  contact?: Contact
  onSubmit: (values: ContactFormValues) => Promise<void>
  onCancel: () => void
}

export function ContactForm({ contact, onSubmit, onCancel }: ContactFormProps) {
  return (
    <EntityForm<ContactFormValues>
      schema={contactFormSchema}
      fields={fields}
      defaultValues={contactFormDefaults(contact)}
      onSubmit={onSubmit}
      onCancel={onCancel}
      submitLabel={contact ? "Save changes" : "Add contact"}
    />
  )
}
