/*
  Reliefs module: loss reliefs and other reclaims with their qualifying
  windows. A watchlist banner flags windows closing within 90 days
  (GET /reliefs/watchlist), the table lists every relief with its linked
  asset and deadline, and writers can create, edit and archive records.
*/

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { TriangleAlert } from "lucide-react"

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
import { api, ApiError, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import {
  useArchiveResource,
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"
import type { Asset } from "@/lib/types"

import { ReliefForm } from "./relief-form"
import {
  daysUntil,
  reliefTypeBadgeLabel,
  reliefTypeLabel,
  reliefWatchlistKey,
  toReliefPayload,
  type Relief,
  type ReliefFormValues,
  type ReliefWatchlistItem,
} from "./relief-meta"
import { useEstateId } from "./use-estate-id"

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function buildColumns(
  assetName: (id: string | null) => string | null,
  today: string,
): DataTableColumn<Relief>[] {
  return [
    {
      key: "relief_type",
      header: "Type",
      value: (row) => reliefTypeBadgeLabel(row.relief_type),
      kind: "badge",
    },
    {
      key: "asset",
      header: "Asset",
      value: (row) => assetName(row.asset_id),
    },
    {
      key: "probate_value",
      header: "Probate value",
      value: (row) => row.probate_value,
      kind: "money",
    },
    {
      key: "sale_value",
      header: "Sale value",
      value: (row) => row.sale_value,
      kind: "money",
    },
    {
      key: "sale_date",
      header: "Sale date",
      value: (row) => row.sale_date,
      kind: "date",
    },
    {
      key: "window_deadline",
      header: "Window deadline",
      value: (row) => row.window_deadline,
      render: (row) =>
        row.window_deadline ? (
          <span className="inline-flex flex-wrap items-center gap-2">
            {formatDate(row.window_deadline)}
            {row.window_deadline < today ? (
              <Badge variant="destructive">Overdue</Badge>
            ) : null}
          </span>
        ) : (
          <span aria-hidden="true">&ndash;</span>
        ),
    },
    {
      key: "potential_reclaim",
      header: "Potential reclaim",
      value: (row) => row.potential_reclaim,
      kind: "money",
    },
    { key: "status", header: "Status", value: (row) => row.status },
  ]
}

function WatchlistBanner({ items }: { items: ReliefWatchlistItem[] }) {
  const today = todayIso()
  if (items.length === 0) return null

  return (
    <div
      role="status"
      className="mb-6 rounded-lg border border-amber-400/60 bg-amber-50 px-4 py-3 text-amber-900 dark:border-amber-600/60 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <p className="flex items-center gap-2 text-sm font-semibold">
        <TriangleAlert aria-hidden="true" className="size-4 shrink-0" />
        Relief windows closing within 90 days
      </p>
      <ul className="mt-2 space-y-1 text-sm">
        {items.map((item) => {
          const days =
            typeof item.days_remaining === "number"
              ? item.days_remaining
              : daysUntil(item.window_deadline, today)
          return (
            <li key={item.id}>
              {reliefTypeLabel(item.relief_type)}: deadline{" "}
              {formatDate(item.window_deadline)}
              {days < 0
                ? " (passed)"
                : days === 0
                  ? " (today)"
                  : ` (${days} day${days === 1 ? "" : "s"} left)`}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

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

export default function ReliefsPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const estateId = useEstateId()

  const { data, isPending } = useResourceList<Relief>("/reliefs")
  const assetsQuery = useResourceList<Asset>("/assets")
  const watchlistQuery = useQuery({
    queryKey: reliefWatchlistKey,
    queryFn: async () => {
      try {
        return await api.get<ReliefWatchlistItem[]>("/reliefs/watchlist")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  const create = useCreateResource<Relief>("/reliefs")
  const update = useUpdateResource<Relief>("/reliefs")
  const archive = useArchiveResource<Relief>("/reliefs")

  const [createOpen, setCreateOpen] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [archiveOpen, setArchiveOpen] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const reliefs = React.useMemo(() => data ?? [], [data])
  const assets = React.useMemo(
    () => assetsQuery.data ?? [],
    [assetsQuery.data],
  )
  const selected = reliefs.find((relief) => relief.id === selectedId)

  const assetName = React.useCallback(
    (id: string | null) =>
      id
        ? (assets.find((asset) => asset.id === id)?.description ?? null)
        : null,
    [assets],
  )
  const assetOptions = React.useMemo(
    () =>
      assets.map((asset) => ({ value: asset.id, label: asset.description })),
    [assets],
  )
  const columns = React.useMemo(
    () => buildColumns(assetName, todayIso()),
    [assetName],
  )

  async function handleCreate(values: ReliefFormValues) {
    if (!estateId) {
      throw new ApiError(
        0,
        "The estate details are still loading. Please try again in a moment.",
      )
    }
    await create.mutateAsync({
      estate_id: estateId,
      ...toReliefPayload(values),
    })
    setCreateOpen(false)
  }

  async function handleEdit(values: ReliefFormValues) {
    if (!selected) return
    await update.mutateAsync({
      id: selected.id,
      data: toReliefPayload(values),
    })
    setEditOpen(false)
  }

  async function handleArchive(reason: string) {
    if (!selected) return
    await archive.mutateAsync({ id: selected.id, reason })
    setSelectedId(null)
  }

  return (
    <section aria-label="Reliefs">
      <PageHeader
        title="Reliefs"
        description="Loss reliefs and other reclaims, with their qualifying windows and deadlines."
        actionLabel="Add relief"
        onAction={() => setCreateOpen(true)}
      />

      <WatchlistBanner items={watchlistQuery.data ?? []} />

      <DataTable
        columns={columns}
        rows={reliefs}
        rowKey={(row) => row.id}
        isLoading={isPending}
        label="Reliefs"
        filterLabel="Filter reliefs"
        emptyTitle="No reliefs tracked yet."
        emptyMessage="Reliefs will appear here as they are added."
        onRowClick={(row) => setSelectedId(row.id)}
      />

      <p className="mt-4 max-w-prose text-xs text-muted-foreground">
        The potential reclaim shown is the difference in value only. The
        amount actually reclaimed depends on the estate rate of inheritance
        tax, so the final figure may be lower.
      </p>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add relief</DialogTitle>
            <DialogDescription>
              A relief or reclaim to track, with its qualifying window.
            </DialogDescription>
          </DialogHeader>
          <ReliefForm
            assetOptions={assetOptions}
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
                <DialogTitle>
                  {reliefTypeLabel(selected.relief_type)}
                </DialogTitle>
                <DialogDescription>
                  {selected.status ?? "No status recorded"}
                </DialogDescription>
              </DialogHeader>

              <dl className="divide-y">
                <DetailRow label="Type">
                  {reliefTypeLabel(selected.relief_type)}
                </DetailRow>
                <DetailRow label="Linked asset">
                  {assetName(selected.asset_id)}
                </DetailRow>
                <DetailRow label="Probate value">
                  {selected.probate_value
                    ? formatMoney(selected.probate_value)
                    : null}
                </DetailRow>
                <DetailRow label="Sale value">
                  {selected.sale_value
                    ? formatMoney(selected.sale_value)
                    : null}
                </DetailRow>
                <DetailRow label="Sale date">
                  {selected.sale_date ? formatDate(selected.sale_date) : null}
                </DetailRow>
                <DetailRow label="Window deadline">
                  {selected.window_deadline
                    ? formatDate(selected.window_deadline)
                    : null}
                </DetailRow>
                <DetailRow label="Deadline basis">
                  {selected.window_basis}
                </DetailRow>
                <DetailRow label="Potential reclaim">
                  {selected.potential_reclaim
                    ? formatMoney(selected.potential_reclaim)
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
                <DialogTitle>Edit relief</DialogTitle>
                <DialogDescription>
                  Changes are saved to the relief record.
                </DialogDescription>
              </DialogHeader>
              <ReliefForm
                relief={selected}
                assetOptions={assetOptions}
                onSubmit={handleEdit}
                onCancel={() => setEditOpen(false)}
              />
            </DialogContent>
          </Dialog>

          <ArchiveDialog
            open={archiveOpen}
            onOpenChange={setArchiveOpen}
            itemLabel="relief"
            onConfirm={handleArchive}
          />
        </>
      ) : null}
    </section>
  )
}
