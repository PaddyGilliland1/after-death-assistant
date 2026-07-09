/*
  Contact detail dialog: every field, the notification tracker with a
  "Mark notified" quick action (PATCH notification_status, notified_date
  and notified_method), and the interactions timeline (newest first) with
  an add-interaction form for writers.
*/

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { formatDate } from "@/components/shared/formatters"
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
import { Input } from "@/components/ui/input"
import { api, isApiError } from "@/lib/api"
import { useUpdateResource } from "@/lib/hooks/use-resource"
import type { Contact } from "@/lib/types"
import { cn } from "@/lib/utils"

import {
  categoryLabel,
  interactionChannelOptions,
  interactionDirectionOptions,
  interactionsKey,
  needsNotifying,
  notifiedMethodOptions,
  sortInteractionsNewestFirst,
  todayIso,
  type ContactInteraction,
} from "./contact-meta"

const controlClass =
  "flex w-full min-w-0 rounded-md border border-input bg-background px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"

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

function text(value: string | null | undefined): React.ReactNode {
  return value ? value : <span aria-hidden="true">&ndash;</span>
}

/* -------------------------------------------------- mark notified dialog */

interface MarkNotifiedDialogProps {
  contact: Contact
  open: boolean
  onOpenChange: (open: boolean) => void
}

function MarkNotifiedDialog({
  contact,
  open,
  onOpenChange,
}: MarkNotifiedDialogProps) {
  const [date, setDate] = React.useState(todayIso())
  const [method, setMethod] = React.useState("letter")
  const [error, setError] = React.useState<string | null>(null)
  const update = useUpdateResource<Contact>("/contacts")
  const dateId = React.useId()
  const methodId = React.useId()

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    try {
      await update.mutateAsync({
        id: contact.id,
        data: {
          notification_status: "notified",
          notified_date: date,
          notified_method: method,
        },
      })
      onOpenChange(false)
    } catch (cause) {
      setError(
        isApiError(cause)
          ? cause.message
          : "Something went wrong while saving. Please try again.",
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Mark {contact.name} as notified</DialogTitle>
            <DialogDescription>
              Records when and how this contact was told of the death.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-1.5">
              <label htmlFor={dateId} className="text-sm font-medium">
                Date notified
              </label>
              <Input
                id={dateId}
                type="date"
                value={date}
                onChange={(event) => setDate(event.target.value)}
                disabled={update.isPending}
              />
            </div>
            <div className="space-y-1.5">
              <label htmlFor={methodId} className="text-sm font-medium">
                Method
              </label>
              <select
                id={methodId}
                value={method}
                onChange={(event) => setMethod(event.target.value)}
                disabled={update.isPending}
                className={cn(controlClass, "h-9")}
              >
                {notifiedMethodOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {error ? (
            <div
              role="alert"
              className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            >
              {error}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving" : "Save notification"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

/* ---------------------------------------------------- interactions panel */

function AddInteractionForm({ contact }: { contact: Contact }) {
  const queryClient = useQueryClient()
  const [date, setDate] = React.useState(todayIso())
  const [channel, setChannel] = React.useState("")
  const [direction, setDirection] = React.useState("")
  const [summary, setSummary] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const dateId = React.useId()
  const channelId = React.useId()
  const directionId = React.useId()
  const summaryId = React.useId()

  const create = useMutation({
    mutationFn: (input: {
      date: string
      channel: string | null
      direction: string | null
      summary: string | null
    }) =>
      api.post<ContactInteraction>(
        `/contacts/${contact.id}/interactions`,
        input,
      ),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: interactionsKey(contact.id) }),
  })

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (!summary.trim()) {
      setError("Please give a short summary of the interaction.")
      return
    }
    try {
      await create.mutateAsync({
        date,
        channel: channel || null,
        direction: direction || null,
        summary: summary.trim(),
      })
      setSummary("")
    } catch (cause) {
      setError(
        isApiError(cause)
          ? cause.message
          : "Something went wrong while saving. Please try again.",
      )
    }
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <label htmlFor={dateId} className="text-sm font-medium">
            Date
          </label>
          <Input
            id={dateId}
            type="date"
            value={date}
            onChange={(event) => setDate(event.target.value)}
            disabled={create.isPending}
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={channelId} className="text-sm font-medium">
            Channel
          </label>
          <select
            id={channelId}
            value={channel}
            onChange={(event) => setChannel(event.target.value)}
            disabled={create.isPending}
            className={cn(controlClass, "h-9")}
          >
            <option value="">Choose a channel</option>
            {interactionChannelOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={directionId} className="text-sm font-medium">
            Direction
          </label>
          <select
            id={directionId}
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
            disabled={create.isPending}
            className={cn(controlClass, "h-9")}
          >
            <option value="">Choose a direction</option>
            {interactionDirectionOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div className="space-y-1.5">
        <label htmlFor={summaryId} className="text-sm font-medium">
          Summary
        </label>
        <textarea
          id={summaryId}
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          rows={2}
          disabled={create.isPending}
          placeholder="For example: sent the death certificate by post"
          className={cn(controlClass, "min-h-16 py-2")}
        />
      </div>
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <Button type="submit" size="sm" disabled={create.isPending}>
        {create.isPending ? "Saving" : "Add interaction"}
      </Button>
    </form>
  )
}

function InteractionsTimeline({ contactId }: { contactId: string }) {
  const { data, isPending } = useQuery({
    queryKey: interactionsKey(contactId),
    queryFn: async () => {
      try {
        return await api.get<ContactInteraction[]>(
          `/contacts/${contactId}/interactions`,
        )
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  if (isPending) {
    return <p className="text-sm text-muted-foreground">Loading interactions</p>
  }
  const interactions = sortInteractionsNewestFirst(data ?? [])
  if (interactions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No interactions recorded yet.
      </p>
    )
  }
  return (
    <ol className="space-y-3">
      {interactions.map((interaction) => (
        <li
          key={interaction.id}
          className="border-b pb-3 text-sm last:border-b-0 last:pb-0"
        >
          <p className="flex flex-wrap items-center gap-2">
            <span className="font-medium">
              {formatDate(interaction.date)}
            </span>
            {interaction.channel ? (
              <Badge variant="secondary">
                {interactionChannelOptions.find(
                  (option) => option.value === interaction.channel,
                )?.label ?? interaction.channel}
              </Badge>
            ) : null}
            {interaction.direction ? (
              <Badge variant="outline">
                {interactionDirectionOptions.find(
                  (option) => option.value === interaction.direction,
                )?.label ?? interaction.direction}
              </Badge>
            ) : null}
          </p>
          {interaction.summary ? (
            <p className="mt-1">{interaction.summary}</p>
          ) : null}
        </li>
      ))}
    </ol>
  )
}

/* ---------------------------------------------------------- detail dialog */

export interface ContactDetailDialogProps {
  contact: Contact
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Whether the current role can create or change records. */
  canWrite: boolean
  onEdit: () => void
  onArchive: () => void
}

export function ContactDetailDialog({
  contact,
  open,
  onOpenChange,
  canWrite,
  onEdit,
  onArchive,
}: ContactDetailDialogProps) {
  const [markNotifiedOpen, setMarkNotifiedOpen] = React.useState(false)

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>{contact.name}</DialogTitle>
            <DialogDescription>
              {categoryLabel(contact.category)}
              {contact.org ? ` · ${contact.org}` : ""}
            </DialogDescription>
          </DialogHeader>

          <dl className="divide-y">
            <DetailRow label="Category">
              <Badge variant="secondary">
                {categoryLabel(contact.category)}
              </Badge>
            </DetailRow>
            <DetailRow label="Organisation">{text(contact.org)}</DetailRow>
            <DetailRow label="Relationship">
              {text(contact.relationship)}
            </DetailRow>
            <DetailRow label="Email">{text(contact.email)}</DetailRow>
            <DetailRow label="Phone">{text(contact.phone)}</DetailRow>
            <DetailRow label="Address">{text(contact.address)}</DetailRow>
            <DetailRow label="References">
              {contact.references.length > 0
                ? contact.references.join(", ")
                : text(null)}
            </DetailRow>
            <DetailRow label="Holds or handles">
              {text(contact.holds_or_handles)}
            </DetailRow>
            <DetailRow label="Notification required">
              {contact.notify_required ? "Yes" : "No"}
            </DetailRow>
            <DetailRow label="Notification status">
              {contact.notify_required ? (
                <Badge
                  variant={
                    contact.notification_status === "notified"
                      ? "default"
                      : "outline"
                  }
                >
                  {contact.notification_status === "notified"
                    ? "Notified"
                    : "Pending"}
                </Badge>
              ) : (
                text(null)
              )}
            </DetailRow>
            <DetailRow label="Notified date">
              {contact.notified_date
                ? formatDate(contact.notified_date)
                : text(null)}
            </DetailRow>
            <DetailRow label="Notified method">
              {contact.notified_method
                ? (notifiedMethodOptions.find(
                    (option) => option.value === contact.notified_method,
                  )?.label ?? contact.notified_method)
                : text(null)}
            </DetailRow>
          </dl>

          <section aria-label="Interactions" className="space-y-3">
            <h3 className="text-sm font-semibold">Interactions</h3>
            <InteractionsTimeline contactId={contact.id} />
            {canWrite ? <AddInteractionForm contact={contact} /> : null}
          </section>

          <DialogFooter className="gap-2">
            {canWrite && needsNotifying(contact) ? (
              <Button type="button" onClick={() => setMarkNotifiedOpen(true)}>
                Mark notified
              </Button>
            ) : null}
            {canWrite ? (
              <>
                <Button type="button" variant="outline" onClick={onEdit}>
                  Edit
                </Button>
                <Button
                  type="button"
                  variant="destructive"
                  onClick={onArchive}
                >
                  Archive
                </Button>
              </>
            ) : null}
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <MarkNotifiedDialog
        contact={contact}
        open={markNotifiedOpen}
        onOpenChange={setMarkNotifiedOpen}
      />
    </>
  )
}
