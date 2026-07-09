/*
  Timeline module: the estate administration process as a calm vertical
  timeline from GET /process/timeline, with a statutory deadlines panel
  from GET /deadlines. Writers can change a step's status (PATCH
  /process/steps/{id}) and recompute the statutory deadline set (POST
  /deadlines/recompute). Viewers see everything read only.
*/

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { CalendarClock, Check, RefreshCw } from "lucide-react"

import { formatDate, humaniseCode } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import { useResourceList } from "@/lib/hooks/use-resource"
import { cn } from "@/lib/utils"

/* Shapes returned by the P1 backend (app/schemas/collab.py). */

type DerivedStatus = "done" | "current" | "upcoming"

interface TimelineEntry {
  step_id: string
  order: number
  name: string
  stored_status: string | null
  derived_status: DerivedStatus
  deadline_type: string | null
  deadline_date: string | null
}

interface DeadlineReminderEntry {
  kind?: string
  basis?: string
  date?: string
  sent?: boolean
}

interface DeadlineRow {
  id: string
  type: string
  derived_date: string | null
  reminders: DeadlineReminderEntry[]
}

const TIMELINE_PATH = "/process/timeline"
const DEADLINES_PATH = "/deadlines?include_past=true"

const STEP_STATUSES = [
  { value: "not_started", label: "Not started" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
  { value: "blocked", label: "Blocked" },
] as const

type StepStatus = (typeof STEP_STATUSES)[number]["value"]

/** The statutory citation kept in a deadline's reminders JSON, if any. */
function citationFor(deadline: DeadlineRow | undefined): string | null {
  if (!deadline) return null
  const entry = deadline.reminders.find(
    (reminder) => reminder.kind === "citation" && reminder.basis,
  )
  return entry?.basis ?? null
}

function derivedStatusBadge(status: DerivedStatus): React.ReactNode {
  switch (status) {
    case "done":
      return <Badge variant="secondary">Done</Badge>
    case "current":
      return <Badge>Current</Badge>
    default:
      return <Badge variant="outline">Upcoming</Badge>
  }
}

function StepMarker({ status }: { status: DerivedStatus }) {
  if (status === "done") {
    return (
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-full border bg-secondary text-secondary-foreground"
      >
        <Check className="size-4" />
      </span>
    )
  }
  if (status === "current") {
    return (
      <span
        aria-hidden="true"
        className="flex size-7 shrink-0 items-center justify-center rounded-full border-2 border-primary bg-background"
      >
        <span className="size-2.5 rounded-full bg-primary" />
      </span>
    )
  }
  return (
    <span
      aria-hidden="true"
      className="flex size-7 shrink-0 items-center justify-center rounded-full border border-dashed bg-background"
    >
      <span className="size-2 rounded-full bg-muted-foreground/40" />
    </span>
  )
}

function TimelinePlaceholder() {
  return (
    <div className="space-y-4" aria-hidden="true">
      {Array.from({ length: 4 }, (_, index) => (
        <div key={index} className="flex items-center gap-4">
          <Skeleton className="size-7 rounded-full" />
          <Skeleton className="h-5 flex-1" />
        </div>
      ))}
    </div>
  )
}

interface TimelineStepProps {
  entry: TimelineEntry
  citation: string | null
  writer: boolean
  onStatusChange: (stepId: string, status: StepStatus) => void
  isSaving: boolean
}

function TimelineStep({
  entry,
  citation,
  writer,
  onStatusChange,
  isSaving,
}: TimelineStepProps) {
  const selectId = React.useId()
  const isCurrent = entry.derived_status === "current"
  const isDone = entry.derived_status === "done"

  return (
    <li className="relative flex gap-4 pb-8 last:pb-0">
      <span
        aria-hidden="true"
        className="absolute left-3.5 top-8 h-[calc(100%-2rem)] w-px bg-border"
      />
      <StepMarker status={entry.derived_status} />
      <div
        className={cn(
          "flex-1 rounded-lg border px-4 py-3",
          isCurrent && "border-primary/50 bg-accent/40",
          isDone && "opacity-80",
          entry.derived_status === "upcoming" && "text-muted-foreground",
        )}
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p
            className={cn(
              "text-sm",
              isCurrent ? "font-semibold text-foreground" : "font-medium",
            )}
          >
            <span className="mr-2 text-xs text-muted-foreground">
              {entry.order}.
            </span>
            {entry.name}
          </p>
          <div className="flex items-center gap-2">
            {derivedStatusBadge(entry.derived_status)}
            {writer ? (
              <>
                <label htmlFor={selectId} className="sr-only">
                  Status for {entry.name}
                </label>
                <select
                  id={selectId}
                  value={entry.stored_status ?? "not_started"}
                  disabled={isSaving}
                  onChange={(event) =>
                    onStatusChange(entry.step_id, event.target.value as StepStatus)
                  }
                  className="h-8 rounded-md border border-input bg-background px-2 text-sm shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {STEP_STATUSES.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </>
            ) : null}
          </div>
        </div>
        {entry.deadline_date || entry.deadline_type ? (
          <p className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <CalendarClock aria-hidden="true" className="size-3.5" />
            <span>
              {entry.deadline_type
                ? `${humaniseCode(entry.deadline_type)} deadline`
                : "Deadline"}
              {entry.deadline_date ? `: ${formatDate(entry.deadline_date)}` : ""}
            </span>
            {citation ? <span>({citation})</span> : null}
          </p>
        ) : null}
      </div>
    </li>
  )
}

interface DeadlinesPanelProps {
  deadlines: DeadlineRow[] | null | undefined
  isLoading: boolean
  isError: boolean
  writer: boolean
}

function DeadlinesPanel({
  deadlines,
  isLoading,
  isError,
  writer,
}: DeadlinesPanelProps) {
  const queryClient = useQueryClient()
  const [message, setMessage] = React.useState<string | null>(null)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)

  const recompute = useMutation({
    mutationFn: () =>
      api.post<{ created: number; updated: number }>("/deadlines/recompute"),
    onSuccess: async (result) => {
      setErrorMessage(null)
      setMessage(
        `Deadlines recomputed: ${result.created} added, ${result.updated} updated.`,
      )
      await queryClient.invalidateQueries({ queryKey: [DEADLINES_PATH] })
      await queryClient.invalidateQueries({ queryKey: [TIMELINE_PATH] })
    },
    onError: (error) => {
      setMessage(null)
      setErrorMessage(
        isApiError(error)
          ? error.message
          : "The deadlines could not be recomputed. Please try again.",
      )
    },
  })

  const todayIso = new Date().toISOString().slice(0, 10)
  const rows = (deadlines ?? []).filter((deadline) => deadline.derived_date)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock
            aria-hidden="true"
            className="size-4 text-muted-foreground"
          />
          Deadlines
        </CardTitle>
        <CardDescription>
          Statutory dates derived from the estate&apos;s records.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading ? (
          <div className="space-y-3" aria-hidden="true">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-4 w-full" />
            ))}
          </div>
        ) : isError || deadlines === null ? (
          <p className="text-sm text-muted-foreground">
            Deadlines are not available yet. They will appear here once the
            estate details are in place.
          </p>
        ) : rows.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No deadlines recorded yet.
            {writer ? " Use the button below to derive the statutory set." : ""}
          </p>
        ) : (
          <ul className="space-y-3">
            {rows.map((deadline) => {
              const overdue =
                deadline.derived_date !== null &&
                deadline.derived_date < todayIso
              const citation = citationFor(deadline)
              return (
                <li
                  key={deadline.id}
                  className="border-b pb-3 text-sm last:border-b-0 last:pb-0"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span>{humaniseCode(deadline.type)}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      {overdue ? (
                        <Badge variant="destructive">Overdue</Badge>
                      ) : null}
                      <span className="text-muted-foreground">
                        {formatDate(deadline.derived_date)}
                      </span>
                    </span>
                  </div>
                  {citation ? (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {citation}
                    </p>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}

        {writer ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => recompute.mutate()}
            disabled={recompute.isPending}
          >
            <RefreshCw aria-hidden="true" />
            {recompute.isPending ? "Recomputing" : "Recompute deadlines"}
          </Button>
        ) : null}

        {message ? (
          <p role="status" className="text-sm text-muted-foreground">
            {message}
          </p>
        ) : null}
        {errorMessage ? (
          <p role="alert" className="text-sm text-destructive">
            {errorMessage}
          </p>
        ) : null}
      </CardContent>
    </Card>
  )
}

export default function TimelinePage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()

  const timelineQuery = useResourceList<TimelineEntry>(TIMELINE_PATH)
  const deadlinesQuery = useResourceList<DeadlineRow>(DEADLINES_PATH)

  const [stepError, setStepError] = React.useState<string | null>(null)

  const stepStatus = useMutation({
    mutationFn: ({ stepId, status }: { stepId: string; status: StepStatus }) =>
      api.patch(`/process/steps/${stepId}`, { status }),
    onSuccess: async () => {
      setStepError(null)
      await queryClient.invalidateQueries({ queryKey: [TIMELINE_PATH] })
      await queryClient.invalidateQueries({ queryKey: ["/process/steps"] })
    },
    onError: (error) => {
      setStepError(
        isApiError(error)
          ? error.message
          : "The step could not be updated. Please try again.",
      )
    },
  })

  const deadlinesByType = React.useMemo(() => {
    const map = new Map<string, DeadlineRow>()
    for (const deadline of deadlinesQuery.data ?? []) {
      map.set(deadline.type, deadline)
    }
    return map
  }, [deadlinesQuery.data])

  const entries = timelineQuery.data ?? []

  return (
    <section aria-label="Timeline">
      <PageHeader
        title="Timeline"
        description="The whole process, step by step, from registering the death to the final distribution."
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          {timelineQuery.isPending ? (
            <TimelinePlaceholder />
          ) : timelineQuery.isError || timelineQuery.data === null ? (
            <p className="text-sm text-muted-foreground">
              The timeline is not available yet. It will appear here once the
              server is connected and the process steps are seeded.
            </p>
          ) : entries.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              The timeline will appear once the process steps are seeded.
            </p>
          ) : (
            <>
              {stepError ? (
                <p role="alert" className="mb-4 text-sm text-destructive">
                  {stepError}
                </p>
              ) : null}
              <ol aria-label="Process steps">
                {entries.map((entry) => (
                  <TimelineStep
                    key={entry.step_id}
                    entry={entry}
                    citation={
                      entry.deadline_type
                        ? citationFor(deadlinesByType.get(entry.deadline_type))
                        : null
                    }
                    writer={writer}
                    isSaving={stepStatus.isPending}
                    onStatusChange={(stepId, status) =>
                      stepStatus.mutate({ stepId, status })
                    }
                  />
                ))}
              </ol>
            </>
          )}
        </div>

        <div>
          <DeadlinesPanel
            deadlines={deadlinesQuery.data}
            isLoading={deadlinesQuery.isPending}
            isError={deadlinesQuery.isError}
            writer={writer}
          />
        </div>
      </div>
    </section>
  )
}
