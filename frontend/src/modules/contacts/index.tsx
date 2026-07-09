/*
  Contacts module: everyone connected to the estate with the notification
  tracker. A DataTable with All / To notify presets, create and edit forms
  over the full category enum, archive with a reason, and a detail dialog
  with the interactions timeline and "Mark notified" quick action.
*/

import * as React from "react"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { PageHeader } from "@/components/shared/page-header"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import type { Contact } from "@/lib/types"

import { ContactForm } from "./contact-form"
import { ContactDetailDialog } from "./contact-detail"
import {
  categoryLabel,
  needsNotifying,
  toContactPayload,
  type ContactFormValues,
} from "./contact-meta"
import { useEstateId } from "./use-estate-id"

type Preset = "all" | "to_notify"

const columns: DataTableColumn<Contact>[] = [
  { key: "name", header: "Name", value: (row) => row.name },
  { key: "org", header: "Organisation", value: (row) => row.org },
  {
    key: "category",
    header: "Category",
    value: (row) => categoryLabel(row.category),
    kind: "badge",
  },
  {
    key: "relationship",
    header: "Relationship",
    value: (row) => row.relationship,
  },
  {
    key: "notify_required",
    header: "Notify required",
    value: (row) => (row.notify_required ? "Yes" : "No"),
  },
  {
    key: "notification_status",
    header: "Notification",
    value: (row) =>
      row.notify_required
        ? row.notification_status === "notified"
          ? "Notified"
          : "Pending"
        : null,
    kind: "badge",
    badgeVariant: (row) =>
      row.notification_status === "notified" ? "default" : "outline",
  },
  {
    key: "notified_date",
    header: "Notified date",
    value: (row) => row.notified_date,
    kind: "date",
  },
]

export default function ContactsPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const estateId = useEstateId()

  const { data, isPending } = useResourceList<Contact>("/contacts")
  const create = useCreateResource<Contact>("/contacts")
  const update = useUpdateResource<Contact>("/contacts")
  const archive = useArchiveResource<Contact>("/contacts")

  const [preset, setPreset] = React.useState<Preset>("all")
  const [createOpen, setCreateOpen] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [archiveOpen, setArchiveOpen] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const contacts = React.useMemo(() => data ?? [], [data])
  const selected = contacts.find((contact) => contact.id === selectedId)

  const rows =
    preset === "to_notify" ? contacts.filter(needsNotifying) : contacts

  async function handleCreate(values: ContactFormValues) {
    if (!estateId) {
      throw new ApiError(
        0,
        "The estate details are still loading. Please try again in a moment.",
      )
    }
    await create.mutateAsync({
      estate_id: estateId,
      ...toContactPayload(values),
    })
    setCreateOpen(false)
  }

  async function handleEdit(values: ContactFormValues) {
    if (!selected) return
    await update.mutateAsync({
      id: selected.id,
      data: toContactPayload(values),
    })
    setEditOpen(false)
  }

  async function handleArchive(reason: string) {
    if (!selected) return
    await archive.mutateAsync({ id: selected.id, reason })
    setSelectedId(null)
  }

  return (
    <section aria-label="Contacts">
      <PageHeader
        title="Contacts"
        description="Organisations and people connected to the estate, with notification tracking."
        actionLabel="Add contact"
        onAction={() => setCreateOpen(true)}
      />

      <div
        role="group"
        aria-label="Filter contacts"
        className="mb-4 flex gap-2"
      >
        <Button
          type="button"
          size="sm"
          variant={preset === "all" ? "default" : "outline"}
          aria-pressed={preset === "all"}
          onClick={() => setPreset("all")}
        >
          All
        </Button>
        <Button
          type="button"
          size="sm"
          variant={preset === "to_notify" ? "default" : "outline"}
          aria-pressed={preset === "to_notify"}
          onClick={() => setPreset("to_notify")}
        >
          To notify
        </Button>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        isLoading={isPending}
        label="Contacts"
        filterLabel="Filter contacts"
        emptyTitle={
          preset === "to_notify"
            ? "No contacts are waiting to be notified."
            : "No contacts recorded yet."
        }
        emptyMessage={
          preset === "to_notify"
            ? "Contacts appear here when they are marked as requiring notification."
            : "Contacts will appear here as they are added."
        }
        onRowClick={(row) => setSelectedId(row.id)}
      />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add contact</DialogTitle>
            <DialogDescription>
              A person or organisation connected to the estate.
            </DialogDescription>
          </DialogHeader>
          <ContactForm
            onSubmit={handleCreate}
            onCancel={() => setCreateOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {selected ? (
        <>
          <ContactDetailDialog
            contact={selected}
            open={!editOpen && !archiveOpen}
            onOpenChange={(open) => {
              if (!open) setSelectedId(null)
            }}
            canWrite={writer}
            onEdit={() => setEditOpen(true)}
            onArchive={() => setArchiveOpen(true)}
          />

          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Edit {selected.name}</DialogTitle>
                <DialogDescription>
                  Changes are saved to the contact record.
                </DialogDescription>
              </DialogHeader>
              <ContactForm
                contact={selected}
                onSubmit={handleEdit}
                onCancel={() => setEditOpen(false)}
              />
            </DialogContent>
          </Dialog>

          <ArchiveDialog
            open={archiveOpen}
            onOpenChange={setArchiveOpen}
            itemLabel="contact"
            onConfirm={handleArchive}
          />
        </>
      ) : null}
    </section>
  )
}
