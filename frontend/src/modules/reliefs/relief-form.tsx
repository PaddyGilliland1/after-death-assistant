/*
  Create and edit form for a relief, built on the shared EntityForm. The
  asset select is populated from the caller's asset list; the caller maps
  validated values to a payload with toReliefPayload and performs the
  mutation.
*/

import * as React from "react"

import {
  EntityForm,
  type EntityField,
  type SelectOption,
} from "@/components/shared/entity-form"

import {
  reliefFormDefaults,
  reliefFormSchema,
  reliefTypeOptions,
  type Relief,
  type ReliefFormValues,
} from "./relief-meta"

export interface ReliefFormProps {
  /** When set, the form edits this relief; otherwise it creates one. */
  relief?: Relief
  /** Options for the linked asset select, from GET /assets. */
  assetOptions: SelectOption[]
  onSubmit: (values: ReliefFormValues) => Promise<void>
  onCancel: () => void
}

export function ReliefForm({
  relief,
  assetOptions,
  onSubmit,
  onCancel,
}: ReliefFormProps) {
  const fields = React.useMemo<EntityField<ReliefFormValues>[]>(
    () => [
      {
        name: "relief_type",
        label: "Relief type",
        kind: "select",
        options: reliefTypeOptions,
      },
      {
        name: "asset_id",
        label: "Linked asset",
        kind: "select",
        options: assetOptions,
        required: false,
        placeholder: "No linked asset",
      },
      {
        name: "probate_value",
        label: "Probate value",
        kind: "money",
        required: false,
      },
      {
        name: "sale_value",
        label: "Sale value",
        kind: "money",
        required: false,
      },
      { name: "sale_date", label: "Sale date", kind: "date", required: false },
      {
        name: "window_deadline",
        label: "Window deadline",
        kind: "date",
        required: false,
        description:
          "Leave blank for IHT35 and IHT38 and the statutory window is derived from the date of death.",
      },
      {
        name: "potential_reclaim",
        label: "Potential reclaim",
        kind: "money",
        required: false,
        description:
          "Leave blank to derive it from the probate and sale values. It is the difference in value only; the amount actually reclaimed depends on the estate rate of inheritance tax.",
      },
      {
        name: "status",
        label: "Status",
        kind: "text",
        required: false,
        placeholder: "For example: monitoring, claimed, received",
      },
    ],
    [assetOptions],
  )

  return (
    <EntityForm<ReliefFormValues>
      schema={reliefFormSchema}
      fields={fields}
      defaultValues={reliefFormDefaults(relief)}
      onSubmit={onSubmit}
      onCancel={onCancel}
      submitLabel={relief ? "Save changes" : "Add relief"}
    />
  )
}
