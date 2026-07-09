/*
  Veteran checklist module: a calm, read only support checklist for
  estates of members and veterans of the armed forces, from
  GET /veteran/checklist. Writers can push the items into the task list
  with POST /veteran/seed-tasks and see the result inline.
*/

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Check, ExternalLink, ListPlus } from "lucide-react"

import { humaniseCode } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"

/* Shapes of GET /veteran/checklist (VeteranChecklistEntry in
   backend/app/schemas/trackers.py), read tolerantly. */

interface ChecklistItem {
  order?: number
  title?: string
  text?: string
  name?: string
  item?: string
  description?: string | null
  url?: string | null
  status?: string | null
  task_status?: string | null
  task_id?: string | null
  [key: string]: unknown
}

type ChecklistResponse = ChecklistItem[] | { items?: ChecklistItem[] }

const CHECKLIST_KEY = ["/veteran/checklist"] as const

function checklistItems(
  response: ChecklistResponse | null | undefined,
): ChecklistItem[] {
  if (!response) return []
  if (Array.isArray(response)) return response
  return response.items ?? []
}

function itemTitle(item: ChecklistItem): string {
  for (const key of ["title", "text", "name", "item"] as const) {
    const value = item[key]
    if (typeof value === "string" && value) return value
  }
  return "Checklist item"
}

function itemStatus(item: ChecklistItem): string | null {
  const value = item.status ?? item.task_status
  return typeof value === "string" && value ? value : null
}

const DONE_STATUSES = new Set(["done", "complete", "completed", "closed"])
const ACTIVE_STATUSES = new Set(["in_progress", "active", "started"])

function StatusBadge({ status }: { status: string | null }) {
  if (!status) return <Badge variant="outline">Not started</Badge>
  const normalised = status.toLowerCase()
  if (DONE_STATUSES.has(normalised)) {
    return (
      <Badge variant="secondary">
        <Check aria-hidden="true" className="mr-1 size-3" />
        Done
      </Badge>
    )
  }
  if (ACTIVE_STATUSES.has(normalised)) {
    return <Badge>In progress</Badge>
  }
  return <Badge variant="outline">{humaniseCode(status)}</Badge>
}

/** A short human message for POST /veteran/seed-tasks. The backend
 *  returns VeteranSeedResult {created: [titles], skipped: [titles]};
 *  plain counts are tolerated too. */
function seedResultMessage(result: unknown): string {
  if (result && typeof result === "object") {
    const record = result as Record<string, unknown>
    const countOf = (value: unknown): number | undefined =>
      typeof value === "number"
        ? value
        : Array.isArray(value)
          ? value.length
          : undefined
    const created = countOf(record.created)
    const skipped = countOf(record.skipped)
    if (created !== undefined) {
      const base = `${created} task${created === 1 ? "" : "s"} added to the task list`
      return skipped
        ? `${base}, ${skipped} already existed.`
        : `${base}.`
    }
  }
  return "The checklist items were added to the task list."
}

export default function VeteranPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()

  const { data, isPending, isError } = useQuery({
    queryKey: CHECKLIST_KEY,
    queryFn: async (): Promise<ChecklistResponse | null> => {
      try {
        return await api.get<ChecklistResponse>("/veteran/checklist")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  const [message, setMessage] = React.useState<string | null>(null)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)

  const seed = useMutation({
    mutationFn: () => api.post<unknown>("/veteran/seed-tasks"),
    onSuccess: async (result) => {
      setErrorMessage(null)
      setMessage(seedResultMessage(result))
      await queryClient.invalidateQueries({ queryKey: CHECKLIST_KEY })
      await queryClient.invalidateQueries({ queryKey: ["/tasks"] })
    },
    onError: (error) => {
      setMessage(null)
      setErrorMessage(
        isApiError(error)
          ? error.message
          : "The tasks could not be created. Please try again.",
      )
    },
  })

  const items = checklistItems(data)

  return (
    <section aria-label="Veteran checklist">
      <PageHeader
        title="Veteran checklist"
        description="Service related notifications, entitlements and organisations to inform."
      >
        {writer ? (
          <Button
            type="button"
            variant="outline"
            onClick={() => seed.mutate()}
            disabled={seed.isPending}
          >
            <ListPlus aria-hidden="true" />
            {seed.isPending ? "Adding" : "Add these to tasks"}
          </Button>
        ) : null}
      </PageHeader>

      <p className="mb-6 max-w-prose text-sm text-muted-foreground">
        This is a support checklist for estates where the person who died
        served in the armed forces. It covers service pensions, medals and
        the main service charities. None of it is compulsory; use what
        applies and skip the rest.
      </p>

      {message ? (
        <p role="status" className="mb-4 text-sm text-muted-foreground">
          {message}
        </p>
      ) : null}
      {errorMessage ? (
        <p role="alert" className="mb-4 text-sm text-destructive">
          {errorMessage}
        </p>
      ) : null}

      {isPending ? (
        <div className="space-y-3" aria-hidden="true">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-12 w-full rounded-lg" />
          ))}
        </div>
      ) : isError || data === null ? (
        <p className="text-sm text-muted-foreground">
          The checklist is not available yet. It will appear here once the
          server is connected.
        </p>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="font-medium">No checklist items yet.</p>
            <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
              The checklist will appear here once it is seeded on the
              server.
            </p>
          </CardContent>
        </Card>
      ) : (
        <ul aria-label="Checklist items" className="space-y-3">
          {items.map((item, index) => (
            <li
              key={index}
              className="flex items-start justify-between gap-4 rounded-lg border px-4 py-3"
            >
              <div>
                <p className="text-sm font-medium">{itemTitle(item)}</p>
                {typeof item.description === "string" && item.description ? (
                  <p className="mt-1 max-w-prose text-sm text-muted-foreground">
                    {item.description}
                  </p>
                ) : null}
                {typeof item.url === "string" && item.url ? (
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-flex items-center gap-1 text-sm underline underline-offset-4 hover:text-foreground/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  >
                    Guidance
                    <ExternalLink
                      aria-hidden="true"
                      className="size-3.5 text-muted-foreground"
                    />
                    <span className="sr-only">
                      {" "}
                      for {itemTitle(item)} (opens in a new tab)
                    </span>
                  </a>
                ) : null}
              </div>
              <div className="shrink-0">
                <StatusBadge status={itemStatus(item)} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
