/*
  Asset tracing module: a read only completeness dashboard from
  GET /tracing/completeness. It surfaces what still needs chasing (assets
  valued on an estimate, contacts not yet notified, outstanding debtors,
  unconfirmed holdings) and links to the official search routes for
  finding unclaimed or forgotten assets.
*/

import type * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { ExternalLink } from "lucide-react"

import { formatMoney } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { StatCard } from "@/components/shared/stat-card"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"

/* Shapes of GET /tracing/completeness (TracingCompletenessRead in
   backend/app/schemas/trackers.py). List entries render tolerantly. */

interface SearchRoute {
  name: string
  url: string
  covers?: string | null
}

interface TracingCompleteness {
  estimated_value_assets?: unknown[]
  unnotified_contacts_count?: number
  outstanding_debtors?: unknown[]
  unconfirmed_unlisted_holdings?: unknown[]
  search_suggestions?: SearchRoute[]
  warning?: string | null
}

const COMPLETENESS_KEY = ["/tracing", "completeness"] as const

/** A readable label for a list entry, whatever shape the backend sends. */
function entryLabel(item: unknown): string {
  if (typeof item === "string") return item
  if (item && typeof item === "object") {
    const record = item as Record<string, unknown>
    for (const key of [
      "description",
      "name",
      "title",
      "holder",
      "service",
      "type",
    ]) {
      const value = record[key]
      if (typeof value === "string" && value) return value
    }
  }
  return "Unnamed record"
}

/** A supporting amount for a list entry, when the backend provides one. */
function entryAmount(item: unknown): string | null {
  if (!item || typeof item !== "object") return null
  const record = item as Record<string, unknown>
  for (const key of ["outstanding", "amount_expected", "amount", "dod_value"]) {
    const value = record[key]
    if (typeof value === "string" || typeof value === "number") {
      const formatted = formatMoney(value)
      if (formatted) return formatted
    }
  }
  return null
}

interface ListSectionProps {
  title: string
  description: string
  items: unknown[]
  emptyMessage: string
}

function ListSection({
  title,
  description,
  items,
  emptyMessage,
}: ListSectionProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{emptyMessage}</p>
        ) : (
          <ul className="space-y-2">
            {items.map((item, index) => {
              const amount = entryAmount(item)
              return (
                <li
                  key={index}
                  className="flex items-center justify-between gap-3 border-b pb-2 text-sm last:border-b-0 last:pb-0"
                >
                  <span>{entryLabel(item)}</span>
                  {amount ? (
                    <span className="shrink-0 tabular-nums text-muted-foreground">
                      {amount}
                    </span>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

function SearchRoutesSection({
  routes,
  warning,
}: {
  routes: SearchRoute[]
  warning?: string | null
}) {
  return (
    <section aria-label="Official search routes" className="mb-8">
      <h2 className="mb-1 text-lg font-semibold tracking-tight">
        Official search routes
      </h2>
      <p className="mb-4 max-w-prose text-sm text-muted-foreground">
        {warning ||
          "Free official services for tracing unclaimed, dormant or forgotten assets."}{" "}
        Each opens in a new tab.
      </p>
      {routes.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No search routes are available yet.
        </p>
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {routes.map((route) => (
            <li key={route.url}>
              <Card className="h-full">
                <CardHeader>
                  <CardTitle className="text-base">
                    <a
                      href={route.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1.5 underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      {route.name}
                      <ExternalLink
                        aria-hidden="true"
                        className="size-3.5 shrink-0 text-muted-foreground"
                      />
                      <span className="sr-only">(opens in a new tab)</span>
                    </a>
                  </CardTitle>
                  {route.covers ? (
                    <CardDescription>{route.covers}</CardDescription>
                  ) : null}
                </CardHeader>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

function LoadingPlaceholder() {
  return (
    <div className="space-y-4" aria-hidden="true">
      <Skeleton className="h-24 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
      <Skeleton className="h-40 w-full rounded-xl" />
    </div>
  )
}

export default function TracingPage() {
  const { data, isPending, isError } = useQuery({
    queryKey: COMPLETENESS_KEY,
    queryFn: async (): Promise<TracingCompleteness | null> => {
      try {
        return await api.get<TracingCompleteness>("/tracing/completeness")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  let content: React.ReactNode
  if (isPending) {
    content = <LoadingPlaceholder />
  } else if (isError || data === null || data === undefined) {
    content = (
      <p className="text-sm text-muted-foreground">
        The completeness summary is not available yet. It will appear here
        once the estate records are in place.
      </p>
    )
  } else {
    content = (
      <>
        <div className="mb-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <StatCard
            label="Contacts not yet notified"
            value={data.unnotified_contacts_count ?? 0}
            description="Institutions that may hold assets and have not been told of the death."
          />
          <StatCard
            label="Assets on an estimate"
            value={(data.estimated_value_assets ?? []).length}
            description="Valuations still to be confirmed in writing."
          />
          <StatCard
            label="Outstanding debtors"
            value={(data.outstanding_debtors ?? []).length}
            description="Money owed to the estate and not yet received."
          />
          <StatCard
            label="Unconfirmed holdings"
            value={(data.unconfirmed_unlisted_holdings ?? []).length}
            description="Possible holdings not yet confirmed by the institution."
          />
        </div>

        <SearchRoutesSection
          routes={data.search_suggestions ?? []}
          warning={data.warning}
        />

        <div className="grid gap-6 lg:grid-cols-2">
          <ListSection
            title="Assets valued on an estimate"
            description="Confirm these valuations before the account is finalised."
            items={data.estimated_value_assets ?? []}
            emptyMessage="Every asset value is confirmed."
          />
          <ListSection
            title="Outstanding debtors"
            description="Money owed to the estate that has not yet arrived."
            items={data.outstanding_debtors ?? []}
            emptyMessage="No outstanding debtors."
          />
          <ListSection
            title="Unconfirmed holdings"
            description="Possible unlisted holdings, such as club shares, that the holder has not yet confirmed."
            items={data.unconfirmed_unlisted_holdings ?? []}
            emptyMessage="No unconfirmed holdings."
          />
        </div>
      </>
    )
  }

  return (
    <section aria-label="Asset tracing">
      <PageHeader
        title="Asset tracing"
        description="How complete the asset picture is, and the official routes for finding anything that has been missed."
      />
      {content}
    </section>
  )
}
