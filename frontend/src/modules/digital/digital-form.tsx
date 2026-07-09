/*
  Create and edit form for a digital asset, built on the shared
  EntityForm. The caller maps validated values to a payload with
  toDigitalPayload and performs the mutation.
*/

import {
  EntityForm,
  type EntityField,
} from "@/components/shared/entity-form"

import {
  digitalFormDefaults,
  digitalFormSchema,
  type DigitalAsset,
  type DigitalFormValues,
} from "./digital-meta"

const fields: EntityField<DigitalFormValues>[] = [
  {
    name: "service",
    label: "Service",
    kind: "text",
    placeholder: "For example: email, streaming service, cloud storage",
  },
  {
    name: "type",
    label: "Type",
    kind: "text",
    required: false,
    placeholder: "For example: subscription, social, email, storage",
  },
  {
    name: "login_known",
    label: "Login known",
    kind: "checkbox",
    description:
      "Tick when the executors know how to access the account. Never record the password itself here.",
  },
  {
    name: "action",
    label: "Action",
    kind: "text",
    required: false,
    placeholder: "For example: close, memorialise, transfer, keep",
  },
  {
    name: "recurring_amount",
    label: "Recurring amount",
    kind: "money",
    required: false,
    description: "The regular charge, if the service still bills the estate.",
  },
  {
    name: "status",
    label: "Status",
    kind: "text",
    required: false,
    placeholder: "For example: open, notified, closed",
  },
]

export interface DigitalFormProps {
  /** When set, the form edits this record; otherwise it creates one. */
  asset?: DigitalAsset
  onSubmit: (values: DigitalFormValues) => Promise<void>
  onCancel: () => void
}

export function DigitalForm({ asset, onSubmit, onCancel }: DigitalFormProps) {
  return (
    <EntityForm<DigitalFormValues>
      schema={digitalFormSchema}
      fields={fields}
      defaultValues={digitalFormDefaults(asset)}
      onSubmit={onSubmit}
      onCancel={onCancel}
      submitLabel={asset ? "Save changes" : "Add digital asset"}
    />
  )
}
