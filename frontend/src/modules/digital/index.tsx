/*
  Digital assets module: online accounts, subscriptions and services with
  what should happen to each. A DataTable of records, a stat card with the
  recurring spend still being billed (GET /digital/recurring-total), and
  create, edit and archive for writers.
*/

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { formatMoney } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { StatCard } from "@/components/shared/stat-card"
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
import { api, ApiError, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import {
  useArchiveResource,
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"

import { DigitalForm } from "./digital-form"
import {
  DIGITAL_ITEMS_PATH,
  readRecurringTotal,
  recurringTotalKey,
  toDigitalPayload,
  type DigitalAsset,
  type DigitalFormValues,
} from "./digital-meta"
import { useEstateId } from "./use-estate-id"

const columns: DataTableColumn<DigitalAsset>[] = [
  { key: "service", header: "Service", value: (row) => row.service },
  {
    key: "type",
    header: "Type",
    value: (row) => row.type,
    render: (row) =>
      row.type ? (
        <Badge variant="secondary">{row.type}</Badge>
      ) : (
        <span aria-hidden="true">&ndash;</span>
      ),
  },
  {
    key: "login_known",
    header: "Login known",
    value: (row) => (row.login_known ? "Yes" : "No"),
  },
  { key: "action", header: "Action", value: (row) => row.action },
  {
    key: "recurring_amount",
    header: "Recurring amount",
    value: (row) => row.recurring_amount,
    kind: "money",
  },
  { key: "status", header: "Status", value: (row) => row.status },
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

export default function DigitalPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const estateId = useEstateId()

  const { data, isPending } = useResourceList<DigitalAsset>(DIGITAL_ITEMS_PATH)
  const totalQuery = useQuery({
    queryKey: recurringTotalKey,
    queryFn: async () => {
      try {
        return await api.get<unknown>("/digital/recurring-total")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  const create = useCreateResource<DigitalAsset>(DIGITAL_ITEMS_PATH)
  const update = useUpdateResource<DigitalAsset>(DIGITAL_ITEMS_PATH)
  const archive = useArchiveResource<DigitalAsset>(DIGITAL_ITEMS_PATH)

  const [createOpen, setCreateOpen] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [archiveOpen, setArchiveOpen] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const records = React.useMemo(() => data ?? [], [data])
  const selected = records.find((record) => record.id === selectedId)

  const recurringTotal = readRecurringTotal(totalQuery.data)

  async function handleCreate(values: DigitalFormValues) {
    if (!estateId) {
      throw new ApiError(
        0,
        "The estate details are still loading. Please try again in a moment.",
      )
    }
    await create.mutateAsync({
      estate_id: estateId,
      ...toDigitalPayload(values),
    })
    setCreateOpen(false)
  }

  async function handleEdit(values: DigitalFormValues) {
    if (!selected) return
    await update.mutateAsync({
      id: selected.id,
      data: toDigitalPayload(values),
    })
    setEditOpen(false)
  }

  async function handleArchive(reason: string) {
    if (!selected) return
    await archive.mutateAsync({ id: selected.id, reason })
    setSelectedId(null)
  }

  return (
    <section aria-label="Digital assets">
      <PageHeader
        title="Digital assets"
        description="Online accounts, subscriptions and services, and what should happen to each."
        actionLabel="Add digital asset"
        onAction={() => setCreateOpen(true)}
      />

      <div className="mb-6 max-w-sm">
        <StatCard
          label="Recurring charges"
          value={
            recurringTotal !== null ? formatMoney(recurringTotal) : null
          }
          description="The total of recurring amounts still being billed to the estate."
          isLoading={totalQuery.isPending}
        />
      </div>

      <DataTable
        columns={columns}
        rows={records}
        rowKey={(row) => row.id}
        isLoading={isPending}
        label="Digital assets"
        filterLabel="Filter digital assets"
        emptyTitle="No digital assets recorded yet."
        emptyMessage="Online accounts and subscriptions will appear here as they are added."
        onRowClick={(row) => setSelectedId(row.id)}
      />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add digital asset</DialogTitle>
            <DialogDescription>
              An online account, subscription or service of the person who
              died.
            </DialogDescription>
          </DialogHeader>
          <DigitalForm
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
                <DialogTitle>{selected.service}</DialogTitle>
                <DialogDescription>
                  {selected.type ?? "Digital asset"}
                </DialogDescription>
              </DialogHeader>

              <dl className="divide-y">
                <DetailRow label="Service">{selected.service}</DetailRow>
                <DetailRow label="Type">{selected.type}</DetailRow>
                <DetailRow label="Login known">
                  {selected.login_known ? "Yes" : "No"}
                </DetailRow>
                <DetailRow label="Action">{selected.action}</DetailRow>
                <DetailRow label="Recurring amount">
                  {selected.recurring_amount
                    ? formatMoney(selected.recurring_amount)
                    : null}
                </DetailRow>
                <DetailRow label="Status">{selected.status}</DetailRow>
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
                <DialogTitle>Edit digital asset</DialogTitle>
                <DialogDescription>
                  Changes are saved to the record.
                </DialogDescription>
              </DialogHeader>
              <DigitalForm
                asset={selected}
                onSubmit={handleEdit}
                onCancel={() => setEditOpen(false)}
              />
            </DialogContent>
          </Dialog>

          <ArchiveDialog
            open={archiveOpen}
            onOpenChange={setArchiveOpen}
            itemLabel="digital asset"
            onConfirm={handleArchive}
          />
        </>
      ) : null}
    </section>
  )
}
