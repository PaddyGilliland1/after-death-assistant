/*
  Valuation history for one asset, shown inside the asset detail dialog:
  GET /assets/{id}/valuations to list, POST to the same path to add. The
  server also refreshes the asset's current value fields on POST, so the
  assets list is invalidated after a successful add.
*/

import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"

import { EntityForm } from "@/components/shared/entity-form"
import { formatDate, formatMoney, humaniseCode } from "@/components/shared/formatters"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useCreateResource,
  useResourceList,
} from "@/lib/hooks/use-resource"

import {
  valuationDefaults,
  valuationFields,
  valuationSchema,
  type ValuationFormValues,
} from "./forms"
import { omitEmpty } from "./payload"
import type { ValuationEvent } from "./types"

export function ValuationsPanel({
  assetId,
  writable,
}: {
  assetId: string
  writable: boolean
}) {
  const path = `/assets/${assetId}/valuations`
  const queryClient = useQueryClient()
  const list = useResourceList<ValuationEvent>(path)
  const create = useCreateResource<ValuationEvent, Record<string, unknown>>(
    path,
  )

  const valuations = React.useMemo(
    () =>
      (list.data ?? [])
        .filter((event) => !event.archived_at)
        .slice()
        .sort((a, b) => b.date.localeCompare(a.date)),
    [list.data],
  )

  async function handleAdd(values: ValuationFormValues) {
    await create.mutateAsync(omitEmpty(values))
    // The server refreshed the asset's current value; refetch the register.
    await queryClient.invalidateQueries({ queryKey: ["/assets"] })
  }

  return (
    <section aria-label="Valuation history" className="space-y-3 border-t pt-4">
      <h3 className="text-sm font-semibold">Valuation history</h3>
      {list.isPending ? (
        <Skeleton className="h-12 w-full" />
      ) : valuations.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No valuations recorded for this asset yet.
        </p>
      ) : (
        <ul className="space-y-2">
          {valuations.map((event) => (
            <li
              key={event.id}
              className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
            >
              <div>
                <p className="font-medium tabular-nums">
                  {formatMoney(event.value)}
                </p>
                <p className="text-muted-foreground">
                  {formatDate(event.date)}
                  {event.source ? ` · ${event.source}` : null}
                </p>
              </div>
              <Badge
                variant={event.basis === "confirmed" ? "default" : "secondary"}
              >
                {humaniseCode(event.basis)}
              </Badge>
            </li>
          ))}
        </ul>
      )}
      {writable ? (
        <div className="space-y-2 border-t pt-4">
          <h4 className="text-sm font-medium">Add a valuation</h4>
          <p className="text-xs text-muted-foreground">
            Adding a valuation also updates the asset's current value.
          </p>
          <EntityForm<ValuationFormValues>
            key={valuations.length}
            schema={valuationSchema}
            fields={valuationFields}
            defaultValues={valuationDefaults}
            onSubmit={handleAdd}
            submitLabel="Add valuation"
          />
        </div>
      ) : null}
    </section>
  )
}
