/*
  The assets register: every asset with its date of death value, current
  value and status. Row click opens a detail dialog with all fields plus
  the valuation history and, for write roles, an add valuation form.
*/

import type { DataTableColumn } from "@/components/shared/data-table"
import { humaniseCode } from "@/components/shared/formatters"
import type { SelectOption } from "@/components/shared/form-schema"
import type { Asset } from "@/lib/types"

import {
  assetCreateDefaults,
  assetEditDefaults,
  assetFields,
  assetSchema,
  type AssetFormValues,
} from "./forms"
import { emptyToNull, omitEmpty } from "./payload"
import {
  RegisterSection,
  type DetailFieldDef,
} from "./register-section"
import { ValuationsPanel } from "./valuations-panel"

export interface AssetsSectionProps {
  estateId: string | null
  contactOptions: SelectOption[]
  contactName: (id: string | null) => string | null
}

export function AssetsSection({
  estateId,
  contactOptions,
  contactName,
}: AssetsSectionProps) {
  const columns: DataTableColumn<Asset>[] = [
    { key: "description", header: "Description", value: (row) => row.description },
    {
      key: "category",
      header: "Category",
      value: (row) => humaniseCode(row.category),
    },
    {
      key: "holder",
      header: "Holder",
      value: (row) => contactName(row.holder_contact_id),
    },
    {
      key: "ownership",
      header: "Ownership",
      value: (row) => humaniseCode(row.ownership),
      kind: "badge",
      badgeVariant: () => "outline",
    },
    {
      key: "dod_value",
      header: "Value at death",
      value: (row) => row.dod_value,
      kind: "money",
    },
    {
      key: "current_value",
      header: "Current value",
      value: (row) => row.current_or_realised_value,
      kind: "money",
    },
    {
      key: "value_basis",
      header: "Basis",
      value: (row) => humaniseCode(row.value_basis),
      kind: "badge",
      badgeVariant: (row) =>
        row.value_basis === "confirmed" ? "default" : "secondary",
    },
    {
      key: "status",
      header: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
      kind: "badge",
    },
  ]

  const detailFields: DetailFieldDef<Asset>[] = [
    { label: "Description", value: (row) => row.description },
    { label: "Category", value: (row) => humaniseCode(row.category) },
    { label: "Sub type", value: (row) => row.sub_type },
    { label: "Holder", value: (row) => contactName(row.holder_contact_id) },
    { label: "Account reference", value: (row) => row.account_reference },
    { label: "Ownership", value: (row) => humaniseCode(row.ownership) },
    {
      label: "Share of ownership (%)",
      value: (row) => row.tic_share_pct,
    },
    {
      label: "Value at date of death",
      value: (row) => row.dod_value,
      kind: "money",
    },
    { label: "Value basis", value: (row) => humaniseCode(row.value_basis) },
    { label: "Valuation source", value: (row) => row.valuation_source },
    { label: "Valuation date", value: (row) => row.valuation_date, kind: "date" },
    {
      label: "Current or realised value",
      value: (row) => row.current_or_realised_value,
      kind: "money",
    },
    { label: "Realised date", value: (row) => row.realised_date, kind: "date" },
    {
      label: "Income since death",
      value: (row) => row.income_since_death,
      kind: "money",
    },
    { label: "IHT schedule", value: (row) => row.iht_schedule },
    {
      label: "Qualifies for RNRB",
      value: (row) => row.rnrb_qualifying,
      kind: "boolean",
    },
    {
      label: "Passes outside the estate",
      value: (row) => row.passes_outside_estate,
      kind: "boolean",
    },
    {
      label: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
    },
  ]

  return (
    <RegisterSection<Asset, AssetFormValues>
      title="Assets"
      description="Everything the estate owns, with its value at the date of death and its current position."
      path="/assets"
      itemLabel="asset"
      addLabel="Add asset"
      tableLabel="Assets register"
      filterLabel="Filter assets"
      emptyTitle="No assets recorded yet."
      emptyMessage="Add each asset as you find it; estimates are fine to start with."
      columns={columns}
      estateId={estateId}
      formSchema={assetSchema}
      formFields={assetFields(contactOptions)}
      createDefaults={assetCreateDefaults}
      editDefaults={assetEditDefaults}
      toCreatePayload={(values, estate) =>
        omitEmpty({ ...values, estate_id: estate })
      }
      toUpdatePayload={(values) => emptyToNull({ ...values })}
      detailTitle={(row) => row.description || "Asset"}
      detailFields={detailFields}
      renderDetailExtra={(row, writable) => (
        <ValuationsPanel assetId={row.id} writable={writable} />
      )}
    />
  )
}
