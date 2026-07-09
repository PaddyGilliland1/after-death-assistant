/*
  A generic register section built entirely from the shared platform
  pieces: a heading with an add button (write roles only), a DataTable,
  a create dialog, a detail dialog listing every field, and edit and
  archive flows launched from the detail dialog.

  Used by the assets module (assets, liabilities) and imported by the
  debtors and creditors module (debtors, creditors, Section 27 notices).
  If a third module needs it, it belongs in src/components/shared/.
*/

import * as React from "react"
import { Plus } from "lucide-react"
import type { DefaultValues, FieldValues } from "react-hook-form"
import type { z } from "zod"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { EntityForm, type EntityField } from "@/components/shared/entity-form"
import { formatDate, formatMoney } from "@/components/shared/formatters"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { canWrite, useMe } from "@/lib/auth"
import {
  useArchiveResource,
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"

/** The minimum shape a register row must have. */
export interface RegisterRow {
  id: string
  archived_at: string | null
}

/** One row of the detail dialog's field list. */
export interface DetailFieldDef<T> {
  label: string
  value: (row: T) => string | number | boolean | null | undefined
  kind?: "text" | "money" | "date" | "boolean"
}

export interface RegisterSectionProps<
  T extends RegisterRow,
  TValues extends FieldValues,
> {
  /** Section heading, e.g. "Assets". */
  title: string
  /** One line under the heading explaining what belongs here. */
  description: string
  /** API resource path, e.g. "/assets". */
  path: string
  /** Lower case singular, e.g. "asset". Used in dialog copy. */
  itemLabel: string
  /** Label for the add button, e.g. "Add asset". */
  addLabel: string
  /** Accessible name for the table. */
  tableLabel: string
  filterLabel: string
  emptyTitle: string
  emptyMessage: string
  columns: DataTableColumn<T>[]
  /** Estate the records belong to; creates are disabled until known. */
  estateId: string | null
  formSchema: z.ZodType<TValues, FieldValues>
  formFields: EntityField<TValues>[]
  createDefaults: DefaultValues<TValues>
  editDefaults: (row: T) => DefaultValues<TValues>
  /** Builds the POST body from validated values plus the estate id. */
  toCreatePayload: (values: TValues, estateId: string) => Record<string, unknown>
  /** Builds the PATCH body from validated values. */
  toUpdatePayload: (values: TValues) => Record<string, unknown>
  detailTitle: (row: T) => string
  detailFields: DetailFieldDef<T>[]
  /** Extra detail dialog content, e.g. valuation history or claims. */
  renderDetailExtra?: (row: T, writable: boolean) => React.ReactNode
}

function DetailValue<T>({
  field,
  row,
}: {
  field: DetailFieldDef<T>
  row: T
}) {
  const raw = field.value(row)
  if (raw === null || raw === undefined || raw === "") {
    return <span aria-hidden="true">&ndash;</span>
  }
  switch (field.kind) {
    case "money":
      return (
        <span className="tabular-nums">
          {formatMoney(raw as string | number)}
        </span>
      )
    case "date":
      return <>{formatDate(String(raw))}</>
    case "boolean":
      return <>{raw ? "Yes" : "No"}</>
    default:
      return <>{String(raw)}</>
  }
}

type OpenDialog = "create" | "detail" | "edit" | "archive" | null

export function RegisterSection<
  T extends RegisterRow,
  TValues extends FieldValues,
>({
  title,
  description,
  path,
  itemLabel,
  addLabel,
  tableLabel,
  filterLabel,
  emptyTitle,
  emptyMessage,
  columns,
  estateId,
  formSchema,
  formFields,
  createDefaults,
  editDefaults,
  toCreatePayload,
  toUpdatePayload,
  detailTitle,
  detailFields,
  renderDetailExtra,
}: RegisterSectionProps<T, TValues>) {
  const { role } = useMe()
  const writable = canWrite(role)
  const headingId = React.useId()

  const list = useResourceList<T>(path)
  const create = useCreateResource<T, Record<string, unknown>>(path)
  const update = useUpdateResource<T, Record<string, unknown>>(path)
  const archive = useArchiveResource<T>(path)

  const [dialog, setDialog] = React.useState<OpenDialog>(null)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const rows = React.useMemo(
    () => (list.data ?? []).filter((row) => !row.archived_at),
    [list.data],
  )
  const selected = rows.find((row) => row.id === selectedId) ?? null

  function closeDialogs() {
    setDialog(null)
    setSelectedId(null)
  }

  async function handleCreate(values: TValues) {
    if (!estateId) {
      throw new Error("The estate is not available yet.")
    }
    await create.mutateAsync(toCreatePayload(values, estateId))
    setDialog(null)
  }

  async function handleUpdate(values: TValues) {
    if (!selected) return
    await update.mutateAsync({ id: selected.id, data: toUpdatePayload(values) })
    closeDialogs()
  }

  async function handleArchive(reason: string) {
    if (!selected) return
    await archive.mutateAsync({ id: selected.id, reason })
    closeDialogs()
  }

  return (
    <section aria-labelledby={headingId} className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 id={headingId} className="text-lg font-semibold tracking-tight">
            {title}
          </h2>
          <p className="mt-1 max-w-prose text-sm text-muted-foreground">
            {description}
          </p>
        </div>
        {writable ? (
          <Button
            type="button"
            onClick={() => setDialog("create")}
            disabled={!estateId}
          >
            <Plus aria-hidden="true" />
            {addLabel}
          </Button>
        ) : null}
      </div>

      <DataTable<T>
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        isLoading={list.isPending}
        label={tableLabel}
        filterLabel={filterLabel}
        emptyTitle={emptyTitle}
        emptyMessage={emptyMessage}
        onRowClick={(row) => {
          setSelectedId(row.id)
          setDialog("detail")
        }}
      />

      {/* Create */}
      <Dialog
        open={dialog === "create"}
        onOpenChange={(open) => {
          if (!open) setDialog(null)
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>{addLabel}</DialogTitle>
            <DialogDescription>
              Fill in what you know now; everything can be updated later.
            </DialogDescription>
          </DialogHeader>
          <EntityForm<TValues>
            schema={formSchema}
            fields={formFields}
            defaultValues={createDefaults}
            onSubmit={handleCreate}
            submitLabel={`Save ${itemLabel}`}
            onCancel={() => setDialog(null)}
          />
        </DialogContent>
      </Dialog>

      {/* Detail */}
      <Dialog
        open={dialog === "detail" && selected !== null}
        onOpenChange={(open) => {
          if (!open) closeDialogs()
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          {selected ? (
            <>
              <DialogHeader>
                <DialogTitle>{detailTitle(selected)}</DialogTitle>
                <DialogDescription>
                  {writable
                    ? `Full details of this ${itemLabel}. Use the buttons below to edit or archive it.`
                    : `Full details of this ${itemLabel}.`}
                </DialogDescription>
              </DialogHeader>
              <dl className="grid gap-x-6 gap-y-3 sm:grid-cols-2">
                {detailFields.map((field) => (
                  <div key={field.label}>
                    <dt className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                      {field.label}
                    </dt>
                    <dd className="mt-0.5 text-sm">
                      <DetailValue field={field} row={selected} />
                    </dd>
                  </div>
                ))}
              </dl>
              {renderDetailExtra?.(selected, writable)}
              {writable ? (
                <DialogFooter>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => setDialog("archive")}
                  >
                    Archive
                  </Button>
                  <Button type="button" onClick={() => setDialog("edit")}>
                    Edit
                  </Button>
                </DialogFooter>
              ) : null}
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Edit */}
      <Dialog
        open={dialog === "edit" && selected !== null}
        onOpenChange={(open) => {
          if (!open) closeDialogs()
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          {selected ? (
            <>
              <DialogHeader>
                <DialogTitle>Edit {itemLabel}</DialogTitle>
                <DialogDescription>
                  Change the details and save. Clearing a field removes its
                  value.
                </DialogDescription>
              </DialogHeader>
              <EntityForm<TValues>
                key={selected.id}
                schema={formSchema}
                fields={formFields}
                defaultValues={editDefaults(selected)}
                onSubmit={handleUpdate}
                submitLabel="Save changes"
                onCancel={() => setDialog("detail")}
                cancelLabel="Back"
              />
            </>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Archive */}
      <ArchiveDialog
        open={dialog === "archive" && selected !== null}
        onOpenChange={(open) => {
          if (!open) closeDialogs()
        }}
        itemLabel={itemLabel}
        onConfirm={handleArchive}
      />
    </section>
  )
}
