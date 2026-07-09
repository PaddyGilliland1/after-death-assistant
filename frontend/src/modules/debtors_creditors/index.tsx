/*
  Debtors and creditors module (P1 registers). Three sections: debtors
  (money owed to the estate), creditors (money the estate owes) and the
  Section 27 creditor notices, headed by the safe to distribute guard
  banner. The generic register scaffolding is shared with the assets
  module (see src/modules/assets/register-section.tsx).
*/

import type { DataTableColumn } from "@/components/shared/data-table"
import { humaniseCode } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import type { Creditor, Debtor } from "@/lib/types"
import { emptyToNull, omitEmpty } from "@/modules/assets/payload"
import {
  RegisterSection,
  type DetailFieldDef,
} from "@/modules/assets/register-section"
import { useEstateId } from "@/modules/assets/use-estate-id"

import {
  creditorCreateDefaults,
  creditorEditDefaults,
  creditorFields,
  creditorSchema,
  debtorCreateDefaults,
  debtorEditDefaults,
  debtorFields,
  debtorSchema,
  type CreditorFormValues,
  type DebtorFormValues,
} from "./forms"
import { NoticesSection } from "./notices-section"
import { SafeToDistributeBanner } from "./safe-banner"

function DebtorsSection({ estateId }: { estateId: string | null }) {
  const columns: DataTableColumn<Debtor>[] = [
    { key: "type", header: "Type", value: (row) => humaniseCode(row.type) },
    {
      key: "amount_expected",
      header: "Expected",
      value: (row) => row.amount_expected,
      kind: "money",
    },
    {
      key: "amount_received",
      header: "Received",
      value: (row) => row.amount_received,
      kind: "money",
    },
    {
      key: "status",
      header: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
      kind: "badge",
    },
    {
      key: "expected_date",
      header: "Expected date",
      value: (row) => row.expected_date,
      kind: "date",
    },
  ]

  const detailFields: DetailFieldDef<Debtor>[] = [
    { label: "Type", value: (row) => humaniseCode(row.type) },
    {
      label: "Amount expected",
      value: (row) => row.amount_expected,
      kind: "money",
    },
    {
      label: "Amount received",
      value: (row) => row.amount_received,
      kind: "money",
    },
    {
      label: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
    },
    {
      label: "Expected date",
      value: (row) => row.expected_date,
      kind: "date",
    },
  ]

  return (
    <RegisterSection<Debtor, DebtorFormValues>
      title="Debtors"
      description="Money owed to the estate, such as refunds, arrears and tax repayments."
      path="/debtors"
      itemLabel="debtor"
      addLabel="Add debtor"
      tableLabel="Debtors register"
      filterLabel="Filter debtors"
      emptyTitle="No debtors recorded yet."
      emptyMessage="Record each amount owed to the estate as it comes to light."
      columns={columns}
      estateId={estateId}
      formSchema={debtorSchema}
      formFields={debtorFields}
      createDefaults={debtorCreateDefaults}
      editDefaults={debtorEditDefaults}
      toCreatePayload={(values, estate) =>
        omitEmpty({ ...values, estate_id: estate })
      }
      toUpdatePayload={(values) => emptyToNull({ ...values })}
      detailTitle={(row) => humaniseCode(row.type) || "Debtor"}
      detailFields={detailFields}
    />
  )
}

function CreditorsSection({ estateId }: { estateId: string | null }) {
  const columns: DataTableColumn<Creditor>[] = [
    { key: "type", header: "Type", value: (row) => humaniseCode(row.type) },
    {
      key: "amount_claimed",
      header: "Claimed",
      value: (row) => row.amount_claimed,
      kind: "money",
    },
    {
      key: "amount_agreed",
      header: "Agreed",
      value: (row) => row.amount_agreed,
      kind: "money",
    },
    {
      key: "amount_paid",
      header: "Paid",
      value: (row) => row.amount_paid,
      kind: "money",
    },
    {
      key: "status",
      header: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
      kind: "badge",
    },
    {
      key: "priority_class",
      header: "Priority class",
      value: (row) =>
        row.priority_class ? humaniseCode(row.priority_class) : null,
      kind: "badge",
      badgeVariant: () => "outline",
    },
  ]

  const detailFields: DetailFieldDef<Creditor>[] = [
    { label: "Type", value: (row) => humaniseCode(row.type) },
    {
      label: "Amount claimed",
      value: (row) => row.amount_claimed,
      kind: "money",
    },
    {
      label: "Amount agreed",
      value: (row) => row.amount_agreed,
      kind: "money",
    },
    { label: "Amount paid", value: (row) => row.amount_paid, kind: "money" },
    {
      label: "Status",
      value: (row) => (row.status ? humaniseCode(row.status) : null),
    },
    {
      label: "Priority class",
      value: (row) =>
        row.priority_class ? humaniseCode(row.priority_class) : null,
    },
  ]

  return (
    <RegisterSection<Creditor, CreditorFormValues>
      title="Creditors"
      description="Money the estate owes, tracked from claim to agreement to payment."
      path="/creditors"
      itemLabel="creditor"
      addLabel="Add creditor"
      tableLabel="Creditors register"
      filterLabel="Filter creditors"
      emptyTitle="No creditors recorded yet."
      emptyMessage="Record each claim against the estate as it arrives."
      columns={columns}
      estateId={estateId}
      formSchema={creditorSchema}
      formFields={creditorFields}
      createDefaults={creditorCreateDefaults}
      editDefaults={creditorEditDefaults}
      toCreatePayload={(values, estate) =>
        omitEmpty({ ...values, estate_id: estate })
      }
      toUpdatePayload={(values) => emptyToNull({ ...values })}
      detailTitle={(row) => humaniseCode(row.type) || "Creditor"}
      detailFields={detailFields}
    />
  )
}

export default function DebtorsCreditorsPage() {
  const { estateId } = useEstateId()

  return (
    <section aria-label="Debtors and creditors">
      <PageHeader
        title="Debtors and creditors"
        description="Money owed to the estate and money the estate owes, tracked to settlement, with the Section 27 notice guard for distribution."
      />
      <SafeToDistributeBanner />
      <div className="space-y-10">
        <DebtorsSection estateId={estateId} />
        <CreditorsSection estateId={estateId} />
        <NoticesSection estateId={estateId} />
      </div>
    </section>
  )
}
