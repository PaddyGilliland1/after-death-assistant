/*
  Decision log v1 (Module 19): the immutable record of executor
  decisions. Lists decisions from GET /decisions, records new ones with
  POST /decisions, and shows the full rationale in a detail dialog.

  Deliberately absent: edit and delete affordances. The log protects the
  executors precisely because entries cannot be rewritten; the backend
  returns 405 for PATCH and DELETE, and this page offers neither. To
  correct a decision, record a new one that refers to it.
*/

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { toast } from "sonner"

import { DataTable, type DataTableColumn } from "@/components/shared/data-table"
import { formatDate } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api, isApiError } from "@/lib/api"
import { useCreateResource, useResourceList } from "@/lib/hooks/use-resource"
import { cn } from "@/lib/utils"
import type { Decision, DecisionOption, IsoDate } from "@/lib/types"

/** Payload for POST /decisions (backend DecisionCreate). made_by is set
 *  server side from the signed-in user. */
interface DecisionCreatePayload {
  estate_id: string
  date: IsoDate
  title: string
  rationale: string | null
  options_considered: DecisionOption[] | null
  agreed_by: string[]
}

/** The estate id, needed for the create payload. undefined while
 *  loading, null when no estate has been set up yet. */
function useEstateId(): string | null | undefined {
  const query = useQuery<{ id: string } | null>({
    queryKey: ["/estate", "settings"],
    queryFn: async () => {
      try {
        return await api.get<{ id: string }>("/estate")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    retry: (failureCount, error) => {
      if (isApiError(error) && error.status === 404) return false
      return failureCount < 2
    },
  })
  if (query.data === undefined) return undefined
  return query.data?.id ?? null
}

const textControlClass =
  "flex w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"

function DecisionCreateForm({
  estateId,
  onDone,
}: {
  estateId: string
  onDone: () => void
}) {
  const create = useCreateResource<Decision, DecisionCreatePayload>(
    "/decisions",
  )
  const formId = React.useId()

  const [title, setTitle] = React.useState("")
  const [date, setDate] = React.useState("")
  const [rationale, setRationale] = React.useState("")
  const [options, setOptions] = React.useState<string[]>([""])
  const [agreedBy, setAgreedBy] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)

  const pending = create.isPending

  function setOption(index: number, value: string) {
    setOptions((current) =>
      current.map((option, i) => (i === index ? value : option)),
    )
  }

  // Removing a row here edits the unsaved form only; nothing recorded is
  // ever deleted.
  function removeOption(index: number) {
    setOptions((current) => current.filter((_, i) => i !== index))
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    if (!title.trim()) {
      setError("Enter a title for the decision.")
      return
    }
    if (!date) {
      setError("Enter the date the decision was made.")
      return
    }
    const emails = agreedBy
      .split(/[\s,;]+/)
      .map((value) => value.trim())
      .filter(Boolean)
    if (emails.some((value) => !value.includes("@"))) {
      setError(
        "Enter the agreeing executors as email addresses separated by commas.",
      )
      return
    }
    const considered = options
      .map((option) => option.trim())
      .filter(Boolean)
      .map((option) => ({ option }))

    setError(null)
    try {
      await create.mutateAsync({
        estate_id: estateId,
        date,
        title: title.trim(),
        rationale: rationale.trim() || null,
        options_considered: considered.length > 0 ? considered : null,
        agreed_by: emails,
      })
      toast.success("Decision recorded")
      onDone()
    } catch (cause) {
      setError(
        isApiError(cause)
          ? cause.message
          : "Something went wrong while saving. Please try again.",
      )
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-5">
      {error ? (
        <div
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {error}
        </div>
      ) : null}

      <div className="space-y-1.5">
        <label htmlFor={`${formId}-title`} className="text-sm font-medium">
          Title
        </label>
        <Input
          id={`${formId}-title`}
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="What was decided"
          disabled={pending}
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor={`${formId}-date`} className="text-sm font-medium">
          Date decided
        </label>
        <Input
          id={`${formId}-date`}
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
          disabled={pending}
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor={`${formId}-rationale`} className="text-sm font-medium">
          Rationale{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <textarea
          id={`${formId}-rationale`}
          value={rationale}
          onChange={(event) => setRationale(event.target.value)}
          rows={4}
          placeholder="Why this was the right course"
          disabled={pending}
          className={cn(textControlClass, "min-h-20 py-2")}
        />
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">
          Options considered{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </legend>
        {options.map((option, index) => (
          <div key={index} className="flex items-center gap-2">
            <label htmlFor={`${formId}-option-${index}`} className="sr-only">
              Option {index + 1}
            </label>
            <Input
              id={`${formId}-option-${index}`}
              value={option}
              onChange={(event) => setOption(index, event.target.value)}
              placeholder={`Option ${index + 1}`}
              disabled={pending}
            />
            {options.length > 1 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => removeOption(index)}
                disabled={pending}
                aria-label={`Remove option ${index + 1}`}
              >
                Remove
              </Button>
            ) : null}
          </div>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => setOptions((current) => [...current, ""])}
          disabled={pending}
        >
          Add another option
        </Button>
      </fieldset>

      <div className="space-y-1.5">
        <label htmlFor={`${formId}-agreed`} className="text-sm font-medium">
          Agreed by{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <Input
          id={`${formId}-agreed`}
          value={agreedBy}
          onChange={(event) => setAgreedBy(event.target.value)}
          placeholder="executor@example.com, another@example.com"
          disabled={pending}
        />
        <p className="text-xs text-muted-foreground">
          Email addresses of the executors who agreed, separated by commas.
        </p>
      </div>

      <p className="text-sm text-muted-foreground">
        Once recorded, this decision cannot be changed or deleted.
      </p>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          onClick={onDone}
          disabled={pending}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={pending}>
          {pending ? "Recording" : "Record this decision"}
        </Button>
      </div>
    </form>
  )
}

function DecisionDetailDialog({
  decision,
  onOpenChange,
}: {
  decision: Decision | null
  onOpenChange: (open: boolean) => void
}) {
  return (
    <Dialog open={decision !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        {decision ? (
          <>
            <DialogHeader>
              <DialogTitle>{decision.title}</DialogTitle>
              <DialogDescription>
                Decided {formatDate(decision.date)} by {decision.made_by}.
                This record cannot be changed.
              </DialogDescription>
            </DialogHeader>
            <dl className="space-y-4 text-sm">
              <div>
                <dt className="font-medium">Rationale</dt>
                <dd className="mt-1 whitespace-pre-wrap text-muted-foreground">
                  {decision.rationale ?? "No rationale recorded."}
                </dd>
              </div>
              {decision.options_considered &&
              decision.options_considered.length > 0 ? (
                <div>
                  <dt className="font-medium">Options considered</dt>
                  <dd className="mt-1">
                    <ul className="list-disc space-y-1 pl-5 text-muted-foreground">
                      {decision.options_considered.map((option, index) => (
                        <li key={index}>
                          {option.option}
                          {option.notes ? ` (${option.notes})` : ""}
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              ) : null}
              <div>
                <dt className="font-medium">Agreed by</dt>
                <dd className="mt-1 text-muted-foreground">
                  {decision.agreed_by.length > 0
                    ? decision.agreed_by.join(", ")
                    : "No other executors recorded."}
                </dd>
              </div>
            </dl>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export default function ExecutorPage() {
  const decisions = useResourceList<Decision>("/decisions")
  const estateId = useEstateId()

  const [createOpen, setCreateOpen] = React.useState(false)
  const [selected, setSelected] = React.useState<Decision | null>(null)

  const columns: DataTableColumn<Decision>[] = [
    { key: "date", header: "Date", value: (row) => row.date, kind: "date" },
    { key: "title", header: "Title", value: (row) => row.title },
    { key: "made_by", header: "Made by", value: (row) => row.made_by },
    {
      key: "agreed_by",
      header: "Agreed by",
      value: (row) => row.agreed_by.join(", "),
      sortable: false,
    },
  ]

  return (
    <section aria-label="Decision log">
      <PageHeader
        title="Decision log"
        description="The record of decisions the executors have made, kept to protect them."
        actionLabel="Record decision"
        onAction={() => setCreateOpen(true)}
      />

      <p
        role="note"
        className="mb-6 rounded-md border bg-muted/50 px-4 py-3 text-sm text-muted-foreground"
      >
        Decisions are immutable: once recorded they cannot be changed or
        deleted. To correct one, record a new decision that refers to it.
      </p>

      {!decisions.isPending &&
      (decisions.data === null || decisions.isError) ? (
        <p role="status" className="text-sm text-muted-foreground">
          The decision log is not available yet. It will appear here once
          the server is connected.
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={decisions.data}
          rowKey={(row) => row.id}
          isLoading={decisions.isPending}
          label="Recorded decisions"
          filterLabel="Filter decisions"
          emptyTitle="No decisions recorded yet."
          emptyMessage="Recorded decisions appear here and cannot be changed once made."
          onRowClick={setSelected}
        />
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Record a decision</DialogTitle>
            <DialogDescription>
              A permanent entry in the decision log. It cannot be changed
              or deleted once recorded.
            </DialogDescription>
          </DialogHeader>
          {estateId ? (
            <DecisionCreateForm
              estateId={estateId}
              onDone={() => setCreateOpen(false)}
            />
          ) : (
            <p className="text-sm text-muted-foreground">
              The estate has not been set up yet, so decisions cannot be
              recorded.
            </p>
          )}
        </DialogContent>
      </Dialog>

      <DecisionDetailDialog
        decision={selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null)
        }}
      />
    </section>
  )
}
