/*
  Draft detail dialog: renders a pending draft's payload appropriately
  for its kind. Form drafts show per-form field tables with the gaps
  list prominent in amber; letter and narration drafts show formatted
  text; task suggestions show a checkable list that decides which
  suggestions the approval materialises ({accepted} indices). The
  Approve button (writers only) hands off to the confirm step owned by
  the page. The payload itself is loaded from the draft document.
*/

import * as React from "react"
import { CheckCircle2 } from "lucide-react"

import { formatDate, humaniseCode } from "@/components/shared/formatters"
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
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"

import {
  draftKind,
  draftSummary,
  formDraftViews,
  formNarrativeOf,
  letterReferencesOf,
  letterTextOf,
  suggestionsOf,
  type FormDraftView,
  type PendingDraft,
} from "./draft-meta"

function GapsList({ gaps }: { gaps: string[] }) {
  if (gaps.length === 0) return null
  return (
    <div
      role="status"
      className="rounded-md border border-amber-600/50 bg-amber-500/10 px-4 py-3"
    >
      <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
        Gaps to resolve before this form is ready
      </p>
      <ul
        aria-label="Gaps"
        className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-900 dark:text-amber-200"
      >
        {gaps.map((gap, index) => (
          <li key={index}>{gap}</li>
        ))}
      </ul>
    </div>
  )
}

function FormView({ view }: { view: FormDraftView }) {
  const heading = [view.form, view.title].filter(Boolean).join(": ")
  return (
    <div className="space-y-3">
      {heading ? <h3 className="text-sm font-semibold">{heading}</h3> : null}
      <GapsList gaps={view.gaps} />
      {view.rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          This form draft carries no field values.
        </p>
      ) : (
        <div className="rounded-md border">
          <Table aria-label={`${view.form ?? "Form"} fields`}>
            <TableHeader>
              <TableRow>
                <TableHead>Field</TableHead>
                <TableHead>Value</TableHead>
                <TableHead>Source</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {view.rows.map((row) => (
                <TableRow key={row.key}>
                  <TableCell>
                    <span className="font-medium">{row.label}</span>
                    {row.fieldRef ? (
                      <span className="block text-xs text-muted-foreground">
                        {row.fieldRef}
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell>
                    {row.value || <span aria-hidden="true">&ndash;</span>}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {row.source ? (
                      humaniseCode(row.source.replaceAll(":", " "))
                    ) : (
                      <span aria-hidden="true">&ndash;</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}

function FormDraftBody({ payload }: { payload: unknown }) {
  const views = formDraftViews(payload)
  const narrative = formNarrativeOf(payload)
  if (views.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        The draft carries no form content yet.
      </p>
    )
  }
  return (
    <div className="space-y-6">
      {narrative ? (
        <p className="whitespace-pre-wrap rounded-md border bg-muted/30 px-4 py-3 text-sm leading-relaxed">
          {narrative}
        </p>
      ) : null}
      {views.map((view, index) => (
        <FormView key={index} view={view} />
      ))}
    </div>
  )
}

function LetterDraftBody({ payload }: { payload: unknown }) {
  const text = letterTextOf(payload)
  const references = letterReferencesOf(payload)
  if (!text) {
    return (
      <p className="text-sm text-muted-foreground">
        The draft carries no letter text yet.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      <div className="max-h-80 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/30 px-4 py-3 text-sm leading-relaxed">
        {text}
      </div>
      {references.length > 0 ? (
        <p className="text-sm text-muted-foreground">
          References quoted: {references.join(", ")}
        </p>
      ) : null}
    </div>
  )
}

interface SuggestionsBodyProps {
  payload: unknown
  accepted: Set<number>
  onToggle: (index: number) => void
}

function SuggestionsBody({ payload, accepted, onToggle }: SuggestionsBodyProps) {
  const suggestions = suggestionsOf(payload)
  if (suggestions.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        The draft carries no task suggestions yet.
      </p>
    )
  }
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">
        Ticked suggestions become tasks when you approve the draft.
        Untick anything you do not want; it will simply not be created.
      </p>
      <ul aria-label="Suggested tasks" className="space-y-2">
        {suggestions.map((suggestion, index) => (
          <li key={index} className="rounded-md border px-3 py-2">
            <label className="flex items-start gap-3 text-sm">
              <input
                type="checkbox"
                checked={accepted.has(index)}
                onChange={() => onToggle(index)}
                className="mt-0.5 size-4"
              />
              <span>
                <span className="font-medium">{suggestion.title}</span>
                {suggestion.description ? (
                  <span className="block text-muted-foreground">
                    {suggestion.description}
                  </span>
                ) : null}
                <span className="mt-1 flex flex-wrap gap-2">
                  {suggestion.dueDate ? (
                    <Badge variant="outline">
                      Due {formatDate(suggestion.dueDate)}
                    </Badge>
                  ) : null}
                  {suggestion.priority ? (
                    <Badge variant="outline">
                      {humaniseCode(suggestion.priority)} priority
                    </Badge>
                  ) : null}
                </span>
              </span>
            </label>
          </li>
        ))}
      </ul>
    </div>
  )
}

export interface DraftDetailDialogProps {
  draft: PendingDraft | null
  /** The draft document's content, once loaded. */
  payload: unknown
  payloadPending: boolean
  payloadError: boolean
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Whether the signed-in user may approve (executor or admin). */
  writer: boolean
  /**
   * Called when the user chooses to approve; the page confirms first.
   * For task suggestions, accepted lists the ticked indices; null means
   * every suggestion (or the draft is not a suggestions draft).
   */
  onApprove: (draft: PendingDraft, accepted: number[] | null) => void
}

export function DraftDetailDialog({
  draft,
  payload,
  payloadPending,
  payloadError,
  open,
  onOpenChange,
  writer,
  onApprove,
}: DraftDetailDialogProps) {
  const kind = draft ? draftKind(draft) : "other"
  const suggestionCount =
    kind === "tasks" ? suggestionsOf(payload).length : 0

  /* Suggestion review state: everything starts ticked (accept all). */
  const [accepted, setAccepted] = React.useState<Set<number>>(new Set())
  const draftId = draft?.approval_id
  React.useEffect(() => {
    setAccepted(new Set(Array.from({ length: suggestionCount }, (_, i) => i)))
  }, [draftId, suggestionCount])

  function toggle(index: number) {
    setAccepted((current) => {
      const next = new Set(current)
      if (next.has(index)) {
        next.delete(index)
      } else {
        next.add(index)
      }
      return next
    })
  }

  function handleApprove() {
    if (!draft) return
    if (kind === "tasks" && accepted.size < suggestionCount) {
      onApprove(draft, [...accepted].sort((a, b) => a - b))
    } else {
      onApprove(draft, null)
    }
  }

  return (
    <Dialog open={open && draft !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        {draft ? (
          <>
            <DialogHeader>
              <DialogTitle>{draftSummary(draft)}</DialogTitle>
              <DialogDescription>
                {draft.created_at
                  ? `Created ${formatDate(draft.created_at)}`
                  : "Created by the assistant"}
                {draft.created_by ? ` by ${draft.created_by}` : ""}. A draft
                has no effect until a person approves it.
              </DialogDescription>
            </DialogHeader>

            <div className="mb-1">
              <Badge variant="outline">Awaiting approval</Badge>
            </div>

            {payloadPending ? (
              <div className="space-y-3" aria-hidden="true">
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-2/3" />
              </div>
            ) : payloadError ? (
              <p role="alert" className="text-sm text-destructive">
                The draft content could not be loaded. Please try again.
              </p>
            ) : kind === "form" ? (
              <FormDraftBody payload={payload} />
            ) : kind === "letter" || kind === "narration" ? (
              <LetterDraftBody payload={payload} />
            ) : kind === "tasks" ? (
              <SuggestionsBody
                payload={payload}
                accepted={accepted}
                onToggle={toggle}
              />
            ) : (
              <pre className="max-h-80 overflow-auto rounded-md border bg-muted/30 px-4 py-3 text-xs">
                {JSON.stringify(payload ?? {}, null, 2)}
              </pre>
            )}

            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => onOpenChange(false)}
              >
                Close
              </Button>
              {writer ? (
                <Button
                  type="button"
                  onClick={handleApprove}
                  disabled={payloadPending}
                >
                  <CheckCircle2 aria-hidden="true" />
                  Approve draft
                </Button>
              ) : null}
            </DialogFooter>
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
