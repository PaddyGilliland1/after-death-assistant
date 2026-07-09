/*
  Costs module: funeral and administration spend with the reimbursement
  workflow. A DataTable of recorded costs, create/edit forms, archive
  with a reason, and the "By type" summary of stored totals from
  GET /costs/by-type.
*/

import * as React from "react"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { formatDate, formatMoney } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import {
  useArchiveResource,
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"
import type { Cost } from "@/lib/types"

import { ByTypeSection } from "./by-type-section"
import { CostForm } from "./cost-form"
import {
  ihtTreatmentLabel,
  toCostPayload,
  type CostFormValues,
} from "./cost-meta"
import { useEstateId } from "./use-estate-id"

const columns: DataTableColumn<Cost>[] = [
  {
    key: "description",
    header: "Description",
    value: (row) => row.description,
    render: (row) => (
      <span className="inline-flex flex-wrap items-center gap-2">
        {row.description}
        {row.executor_private ? (
          <Badge variant="outline">Private</Badge>
        ) : null}
      </span>
    ),
  },
  { key: "category", header: "Category", value: (row) => row.category },
  {
    key: "amount",
    header: "Amount",
    value: (row) => row.amount,
    kind: "money",
  },
  { key: "vat", header: "VAT", value: (row) => row.vat, kind: "money" },
  { key: "date", header: "Date", value: (row) => row.date, kind: "date" },
  { key: "paid_by", header: "Paid by", value: (row) => row.paid_by },
  {
    key: "reimbursement",
    header: "Reimbursement",
    value: (row) =>
      row.reimbursed ? "Reimbursed" : row.reimbursable ? "Reimbursable" : null,
    render: (row) =>
      row.reimbursed ? (
        <Badge variant="default">Reimbursed</Badge>
      ) : row.reimbursable ? (
        <Badge variant="outline">Reimbursable</Badge>
      ) : (
        <span aria-hidden="true">&ndash;</span>
      ),
  },
  {
    key: "iht_treatment",
    header: "IHT treatment",
    value: (row) => ihtTreatmentLabel(row.iht_treatment),
    kind: "badge",
    badgeVariant: (row) =>
      row.iht_treatment === "funeral_deductible" ? "default" : "secondary",
  },
]

function DetailRow({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children ?? <span aria-hidden="true">&ndash;</span>}</dd>
    </div>
  )
}

export default function CostsPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const estateId = useEstateId()

  const { data, isPending } = useResourceList<Cost>("/costs")
  const create = useCreateResource<Cost>("/costs")
  const update = useUpdateResource<Cost>("/costs")
  const archive = useArchiveResource<Cost>("/costs")

  const [createOpen, setCreateOpen] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [archiveOpen, setArchiveOpen] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const costs = React.useMemo(() => data ?? [], [data])
  const selected = costs.find((cost) => cost.id === selectedId)

  async function handleCreate(values: CostFormValues) {
    if (!estateId) {
      throw new ApiError(
        0,
        "The estate details are still loading. Please try again in a moment.",
      )
    }
    await create.mutateAsync({
      estate_id: estateId,
      ...toCostPayload(values),
    })
    setCreateOpen(false)
  }

  async function handleEdit(values: CostFormValues) {
    if (!selected) return
    await update.mutateAsync({
      id: selected.id,
      data: toCostPayload(values),
    })
    setEditOpen(false)
  }

  async function handleArchive(reason: string) {
    if (!selected) return
    await archive.mutateAsync({ id: selected.id, reason })
    setSelectedId(null)
  }

  return (
    <section aria-label="Costs">
      <PageHeader
        title="Costs"
        description="Administration costs, receipts and reimbursements, grouped by type."
        actionLabel="Add cost"
        onAction={() => setCreateOpen(true)}
      />

      <DataTable
        columns={columns}
        rows={costs}
        rowKey={(row) => row.id}
        isLoading={isPending}
        label="Costs"
        filterLabel="Filter costs"
        emptyTitle="No costs recorded yet."
        emptyMessage="Costs will appear here as they are added."
        onRowClick={(row) => setSelectedId(row.id)}
      />

      <ByTypeSection />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add cost</DialogTitle>
            <DialogDescription>
              A cost paid on behalf of the estate.
            </DialogDescription>
          </DialogHeader>
          <CostForm
            onSubmit={handleCreate}
            onCancel={() => setCreateOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {selected ? (
        <>
          <Dialog
            open={!editOpen && !archiveOpen}
            onOpenChange={(open) => {
              if (!open) setSelectedId(null)
            }}
          >
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  {selected.description}
                  {selected.executor_private ? (
                    <Badge variant="outline">Private</Badge>
                  ) : null}
                </DialogTitle>
                <DialogDescription>
                  {selected.category} · {formatMoney(selected.amount)}
                </DialogDescription>
              </DialogHeader>

              <dl className="divide-y">
                <DetailRow label="Category">{selected.category}</DetailRow>
                <DetailRow label="Amount">
                  {formatMoney(selected.amount)}
                </DetailRow>
                <DetailRow label="VAT">
                  {selected.vat ? formatMoney(selected.vat) : null}
                </DetailRow>
                <DetailRow label="Date">{formatDate(selected.date)}</DetailRow>
                <DetailRow label="Paid by">{selected.paid_by}</DetailRow>
                <DetailRow label="Payment method">
                  {selected.payment_method}
                </DetailRow>
                <DetailRow label="Reimbursable">
                  {selected.reimbursable ? "Yes" : "No"}
                </DetailRow>
                <DetailRow label="Reimbursed">
                  {selected.reimbursed
                    ? `Yes${
                        selected.reimbursed_date
                          ? `, ${formatDate(selected.reimbursed_date)}`
                          : ""
                      }`
                    : "No"}
                </DetailRow>
                <DetailRow label="IHT treatment">
                  {ihtTreatmentLabel(selected.iht_treatment)}
                </DetailRow>
              </dl>

              <DialogFooter className="gap-2">
                {writer ? (
                  <>
                    <Button
                      type="button"
                      variant="outline"
                      onClick={() => setEditOpen(true)}
                    >
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={() => setArchiveOpen(true)}
                    >
                      Archive
                    </Button>
                  </>
                ) : null}
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setSelectedId(null)}
                >
                  Close
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>

          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Edit cost</DialogTitle>
                <DialogDescription>
                  Changes are saved to the cost record.
                </DialogDescription>
              </DialogHeader>
              <CostForm
                cost={selected}
                onSubmit={handleEdit}
                onCancel={() => setEditOpen(false)}
              />
            </DialogContent>
          </Dialog>

          <ArchiveDialog
            open={archiveOpen}
            onOpenChange={setArchiveOpen}
            itemLabel="cost"
            onConfirm={handleArchive}
          />
        </>
      ) : null}
    </section>
  )
}
