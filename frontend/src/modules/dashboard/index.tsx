/*
  Dashboard v1: six estate statistics from GET /estate/summary, the latest
  unread alerts from GET /notifications, and the next statutory deadlines
  from GET /deadlines. Every card copes with loading, errors and a backend
  that has not implemented its endpoint yet.
*/

import { Bell, CalendarClock } from "lucide-react"

import {
  formatDate,
  formatMoney,
  humaniseCode,
} from "@/components/shared/formatters"
import { StatCard } from "@/components/shared/stat-card"

import { TimelineProgress } from "./timeline-progress"
import { Badge } from "@/components/ui/badge"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useNotifications } from "@/lib/hooks/use-notifications"
import { useResourceList } from "@/lib/hooks/use-resource"
import { formatCount } from "@/lib/format"
import type { Deadline, EstateSummary } from "@/lib/types"

import { useEstateSummary } from "./use-estate-summary"

interface StatConfig {
  key: keyof EstateSummary
  label: string
  description: string
  kind: "money" | "count"
}

const statConfigs: StatConfig[] = [
  {
    key: "gross_assets_at_dod",
    label: "Gross estate",
    description: "All assets before liabilities",
    kind: "money",
  },
  {
    key: "net_estate",
    label: "Net estate",
    description: "After liabilities and funeral costs",
    kind: "money",
  },
  {
    key: "iht_due",
    label: "Inheritance tax due",
    description: "From the latest assessment",
    kind: "money",
  },
  {
    key: "open_task_count",
    label: "Open tasks",
    description: "Actions still to complete",
    kind: "count",
  },
  {
    key: "unnotified_contact_count",
    label: "Contacts to notify",
    description: "Organisations not yet told",
    kind: "count",
  },
  {
    key: "costs_total",
    label: "Costs to date",
    description: "Funeral and administration spend",
    kind: "money",
  },
]

function statValue(
  summary: EstateSummary | null | undefined,
  config: StatConfig,
): string | null {
  const raw = summary?.[config.key]
  if (raw === null || raw === undefined) return null
  if (config.kind === "money") {
    return formatMoney(raw, "") || null
  }
  return formatCount(Number(raw))
}

function CardPlaceholder({ lines = 3 }: { lines?: number }) {
  return (
    <div className="space-y-3" aria-hidden="true">
      {Array.from({ length: lines }, (_, index) => (
        <Skeleton key={index} className="h-4 w-full" />
      ))}
    </div>
  )
}

function AlertsCard() {
  const { unread, isLoading, isError, isUnavailable } = useNotifications()
  const latest = unread.slice(0, 5)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Bell aria-hidden="true" className="size-4 text-muted-foreground" />
          Alerts
        </CardTitle>
        <CardDescription>Unread notifications for you</CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <CardPlaceholder />
        ) : isError || isUnavailable ? (
          <p className="text-sm text-muted-foreground">
            Alerts are not available yet. They will appear here once the
            server is connected.
          </p>
        ) : latest.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No unread alerts. You are up to date.
          </p>
        ) : (
          <ul className="space-y-3">
            {latest.map((notification) => (
              <li
                key={notification.id}
                className="border-b pb-3 text-sm last:border-b-0 last:pb-0"
              >
                <p>{notification.message}</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {humaniseCode(notification.event_type)}
                  {notification.created_at
                    ? ` · ${formatDate(notification.created_at)}`
                    : null}
                </p>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

/** Dated deadlines, soonest first (overdue ones sort to the top). */
function nextDeadlines(deadlines: Deadline[]): Deadline[] {
  return deadlines
    .filter((deadline) => deadline.derived_date)
    .sort((a, b) =>
      String(a.derived_date).localeCompare(String(b.derived_date)),
    )
    .slice(0, 5)
}

function DeadlinesCard() {
  const { data, isPending, isError } = useResourceList<Deadline>("/deadlines")
  const todayIso = new Date().toISOString().slice(0, 10)
  const upcoming = data ? nextDeadlines(data) : []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock
            aria-hidden="true"
            className="size-4 text-muted-foreground"
          />
          Next deadlines
        </CardTitle>
        <CardDescription>Statutory and derived dates</CardDescription>
      </CardHeader>
      <CardContent>
        {isPending ? (
          <CardPlaceholder />
        ) : isError || data === null ? (
          <p className="text-sm text-muted-foreground">
            Deadlines are not available yet. They will appear here once the
            estate details are in place.
          </p>
        ) : upcoming.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No deadlines are due. New ones appear as records are added.
          </p>
        ) : (
          <ul className="space-y-3">
            {upcoming.map((deadline) => {
              const overdue =
                deadline.derived_date !== null &&
                deadline.derived_date < todayIso
              return (
                <li
                  key={deadline.id}
                  className="flex items-center justify-between gap-3 border-b pb-3 text-sm last:border-b-0 last:pb-0"
                >
                  <span>{humaniseCode(deadline.type)}</span>
                  <span className="flex shrink-0 items-center gap-2">
                    {overdue ? (
                      <Badge variant="destructive">Overdue</Badge>
                    ) : null}
                    <span className="text-muted-foreground">
                      {formatDate(deadline.derived_date)}
                    </span>
                  </span>
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export default function DashboardPage() {
  const { data: summary, isPending, isError } = useEstateSummary()

  return (
    <section aria-label="Dashboard">
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">
          A summary of the estate at a glance. Figures update as records are
          added and confirmed.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {statConfigs.map((config) => (
          <StatCard
            key={config.key}
            label={config.label}
            description={config.description}
            value={statValue(summary, config)}
            isLoading={isPending}
          />
        ))}
      </div>

      {!isPending && (summary === null || isError) ? (
        <p className="mt-6 text-sm text-muted-foreground" role="status">
          The estate summary is not available yet. It will appear here once
          the server is connected and records are in place.
        </p>
      ) : null}

      <div className="mt-8">
        <TimelineProgress />
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <AlertsCard />
        <DeadlinesCard />
      </div>
    </section>
  )
}
