/*
  Admin module: three sections in one place.

  - Activity: the recent-events feed from GET /activity (every read role).
  - Audit: the full audit trail from GET /audit with entity and actor
    filters. The server restricts it to executors and administrators;
    a viewer receives 403 and sees a polite denial state.
  - Search: GET /search?q= across contacts, assets, tasks, documents and
    costs, with typed hits grouped and linked to the owning module.
*/

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Activity, ScrollText, Search } from "lucide-react"
import { Link } from "react-router-dom"

import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { formatDate, humaniseCode } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"
import { useResourceList } from "@/lib/hooks/use-resource"
import { cn } from "@/lib/utils"

/* Shapes returned by the P1 backend (app/schemas/collab.py). */

interface ActivityItem {
  id: string
  actor: string
  action: string
  entity: string
  timestamp: string
}

interface AuditEvent {
  id: string
  actor: string
  action: string
  entity: string
  before: Record<string, unknown> | null
  after: Record<string, unknown> | null
  timestamp: string
}

type SearchHitType = "contact" | "asset" | "task" | "document" | "cost"

interface SearchHit {
  type: SearchHitType
  id: string
  label: string
}

const SEARCH_GROUPS: Array<{
  type: SearchHitType
  heading: string
  route: string
}> = [
  { type: "contact", heading: "Contacts", route: "/contacts" },
  { type: "asset", heading: "Assets", route: "/assets" },
  { type: "task", heading: "Tasks", route: "/tasks" },
  { type: "document", heading: "Documents", route: "/documents" },
  { type: "cost", heading: "Costs", route: "/costs" },
]

type SectionKey = "activity" | "audit" | "search"

const SECTIONS: Array<{
  key: SectionKey
  label: string
  icon: typeof Activity
}> = [
  { key: "activity", label: "Activity", icon: Activity },
  { key: "audit", label: "Audit", icon: ScrollText },
  { key: "search", label: "Search", icon: Search },
]

/** "document:2f3a..." becomes "Document" with the full ref kept as a title. */
function entityTypeLabel(entity: string): string {
  const [kind] = entity.split(":")
  return humaniseCode(kind)
}

function ListPlaceholder({ lines = 5 }: { lines?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className="h-4 w-full" />
      ))}
    </div>
  )
}

function ActivitySection() {
  const { data, isPending, isError } = useResourceList<ActivityItem>("/activity")

  if (isPending) return <ListPlaceholder />
  if (isError || data === null) {
    return (
      <p className="text-sm text-muted-foreground">
        The activity feed is not available yet. It will appear here once the
        server is connected.
      </p>
    )
  }
  if (data.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No activity recorded yet. Changes to the estate&apos;s records will
        appear here.
      </p>
    )
  }

  return (
    <ul aria-label="Recent activity" className="divide-y">
      {data.map((item) => (
        <li
          key={item.id}
          className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-3 text-sm"
        >
          <span>
            <span className="font-medium">{item.actor}</span>{" "}
            <span className="text-muted-foreground">
              {humaniseCode(item.action).toLowerCase()}
            </span>{" "}
            <span title={item.entity}>{entityTypeLabel(item.entity)}</span>
          </span>
          <span className="text-xs text-muted-foreground">
            {formatDate(item.timestamp)}
          </span>
        </li>
      ))}
    </ul>
  )
}

function AuditSection() {
  const [entityInput, setEntityInput] = React.useState("")
  const [actorInput, setActorInput] = React.useState("")
  const [filters, setFilters] = React.useState({ entity: "", actor: "" })
  const entityId = React.useId()
  const actorId = React.useId()

  const query = useQuery<AuditEvent[] | null, Error>({
    queryKey: ["/audit", filters.entity, filters.actor],
    queryFn: async () => {
      const params = new URLSearchParams()
      if (filters.entity) params.set("entity", filters.entity)
      if (filters.actor) params.set("actor", filters.actor)
      const suffix = params.toString() ? `?${params.toString()}` : ""
      try {
        return await api.get<AuditEvent[]>(`/audit${suffix}`)
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    retry: (failureCount, error) => {
      if (isApiError(error) && (error.status === 403 || error.status === 404)) {
        return false
      }
      return failureCount < 2
    },
  })

  const denied = isApiError(query.error) && query.error.status === 403

  const columns: DataTableColumn<AuditEvent>[] = [
    { key: "actor", header: "Actor", value: (row) => row.actor },
    {
      key: "action",
      header: "Action",
      value: (row) => humaniseCode(row.action),
      kind: "badge",
    },
    {
      key: "entity",
      header: "Entity",
      value: (row) => row.entity,
      render: (row) => (
        <span title={row.entity}>{entityTypeLabel(row.entity)}</span>
      ),
    },
    {
      key: "timestamp",
      header: "When",
      value: (row) => row.timestamp,
      kind: "date",
    },
  ]

  if (denied) {
    return (
      <p className="text-sm text-muted-foreground" role="status">
        The full audit trail is only available to executors and
        administrators. Please ask an executor if you need a copy of it.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <form
        className="flex flex-wrap items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          setFilters({
            entity: entityInput.trim(),
            actor: actorInput.trim(),
          })
        }}
      >
        <div className="space-y-1.5">
          <label htmlFor={entityId} className="text-sm font-medium">
            Entity
          </label>
          <Input
            id={entityId}
            value={entityInput}
            onChange={(event) => setEntityInput(event.target.value)}
            placeholder="For example: document"
            className="w-48"
          />
        </div>
        <div className="space-y-1.5">
          <label htmlFor={actorId} className="text-sm font-medium">
            Actor email
          </label>
          <Input
            id={actorId}
            type="email"
            value={actorInput}
            onChange={(event) => setActorInput(event.target.value)}
            placeholder="For example: executor@example.com"
            className="w-64"
          />
        </div>
        <Button type="submit" variant="outline">
          Apply filters
        </Button>
      </form>

      {query.isPending ? (
        <ListPlaceholder />
      ) : query.isError ? (
        <p className="text-sm text-muted-foreground" role="status">
          The audit trail could not be loaded. Please try again.
        </p>
      ) : query.data === null ? (
        <p className="text-sm text-muted-foreground">
          The audit trail is not available yet. It will appear here once the
          server is connected.
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={query.data}
          rowKey={(row) => row.id}
          label="Audit events"
          filterable={false}
          emptyTitle="No audit events match these filters."
          emptyMessage="Every change to the estate's records is written here as it happens."
        />
      )}
    </div>
  )
}

function SearchSection() {
  const [input, setInput] = React.useState("")
  const [submitted, setSubmitted] = React.useState("")
  const searchId = React.useId()

  const enabled = submitted.trim().length >= 2
  const query = useQuery<SearchHit[]>({
    queryKey: ["/search", submitted],
    queryFn: () =>
      api.get<SearchHit[]>(`/search?q=${encodeURIComponent(submitted)}`),
    enabled,
    retry: 1,
  })

  const grouped = React.useMemo(() => {
    const hits = query.data ?? []
    return SEARCH_GROUPS.map((group) => ({
      ...group,
      hits: hits.filter((hit) => hit.type === group.type),
    })).filter((group) => group.hits.length > 0)
  }, [query.data])

  return (
    <div className="space-y-4">
      <form
        role="search"
        className="flex max-w-lg items-end gap-3"
        onSubmit={(event) => {
          event.preventDefault()
          setSubmitted(input)
        }}
      >
        <div className="flex-1 space-y-1.5">
          <label htmlFor={searchId} className="text-sm font-medium">
            Search the estate&apos;s records
          </label>
          <Input
            id={searchId}
            type="search"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="At least two characters"
          />
        </div>
        <Button type="submit">Run search</Button>
      </form>

      {!enabled ? (
        <p className="text-sm text-muted-foreground">
          Search across contacts, assets, tasks, documents and costs. Results
          link to the module that owns each record.
        </p>
      ) : query.isPending ? (
        <ListPlaceholder />
      ) : query.isError ? (
        <p className="text-sm text-muted-foreground" role="status">
          The search could not be run. Please try again.
        </p>
      ) : grouped.length === 0 ? (
        <p className="text-sm text-muted-foreground" role="status">
          Nothing matches &ldquo;{submitted}&rdquo;.
        </p>
      ) : (
        <div className="space-y-6">
          {grouped.map((group) => (
            <section key={group.type} aria-label={group.heading}>
              <h3 className="mb-2 text-sm font-medium uppercase tracking-wider text-muted-foreground">
                {group.heading}
              </h3>
              <ul className="divide-y rounded-xl border">
                {group.hits.map((hit) => (
                  <li key={hit.id}>
                    <Link
                      to={group.route}
                      className="flex items-center justify-between gap-4 px-4 py-3 text-sm hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      <span>{hit.label}</span>
                      <span className="text-xs text-muted-foreground">
                        Open {group.heading.toLowerCase()}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  )
}

export default function AdminPage() {
  const [section, setSection] = React.useState<SectionKey>("activity")

  return (
    <section aria-label="Settings and audit">
      <PageHeader
        title="Settings and audit"
        description="Who did what and when: the activity feed, the audit trail and a search across every record."
      />

      <div
        className="mb-6 flex flex-wrap gap-2"
        role="group"
        aria-label="Admin sections"
      >
        {SECTIONS.map((item) => (
          <Button
            key={item.key}
            type="button"
            variant={section === item.key ? "secondary" : "ghost"}
            aria-pressed={section === item.key}
            onClick={() => setSection(item.key)}
            className={cn(section === item.key && "font-semibold")}
          >
            <item.icon aria-hidden="true" />
            {item.label}
          </Button>
        ))}
      </div>

      {section === "activity" ? <ActivitySection /> : null}
      {section === "audit" ? <AuditSection /> : null}
      {section === "search" ? <SearchSection /> : null}
    </section>
  )
}
