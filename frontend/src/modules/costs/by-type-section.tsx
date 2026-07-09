/*
  "By type" summary for costs, driven by GET /costs/by-type: two small
  tables of stored totals, one by category and one by IHT treatment. The
  totals are sums of recorded costs only; nothing is derived or computed
  beyond that.
*/

import { useQuery } from "@tanstack/react-query"

import { formatMoney } from "@/components/shared/formatters"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { api, isApiError } from "@/lib/api"

import {
  costsByTypeKey,
  ihtTreatmentLabel,
  type CostsByType,
} from "./cost-meta"

interface TotalsTableProps {
  label: string
  rows: { name: string; total: string | number }[]
}

function TotalsTable({ label, rows }: TotalsTableProps) {
  return (
    <Table aria-label={label}>
      <TableHeader>
        <TableRow>
          <TableHead>{label}</TableHead>
          <TableHead className="text-right">Total</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.length === 0 ? (
          <TableRow>
            <TableCell colSpan={2} className="text-muted-foreground">
              No costs recorded yet.
            </TableCell>
          </TableRow>
        ) : (
          rows.map((row) => (
            <TableRow key={row.name}>
              <TableCell>{row.name}</TableCell>
              <TableCell className="text-right tabular-nums">
                {formatMoney(row.total)}
              </TableCell>
            </TableRow>
          ))
        )}
      </TableBody>
    </Table>
  )
}

export function ByTypeSection() {
  const { data, isPending, isError } = useQuery({
    queryKey: costsByTypeKey,
    queryFn: async () => {
      try {
        return await api.get<CostsByType>("/costs/by-type")
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  return (
    <section aria-label="Costs by type" className="mt-8">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">By type</CardTitle>
          <CardDescription>
            Totals are sums of recorded costs, grouped by category and by
            inheritance tax treatment.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isPending ? (
            <div className="space-y-3" aria-hidden="true">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : isError || data === null || data === undefined ? (
            <p className="text-sm text-muted-foreground">
              The by-type summary is not available yet. It will appear here
              once costs are recorded.
            </p>
          ) : (
            <div className="grid gap-6 lg:grid-cols-2">
              <TotalsTable
                label="Category"
                rows={data.by_category.map((row) => ({
                  name: row.category,
                  total: row.total,
                }))}
              />
              <TotalsTable
                label="IHT treatment"
                rows={data.by_iht_treatment.map((row) => ({
                  name: ihtTreatmentLabel(row.iht_treatment),
                  total: row.total,
                }))}
              />
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  )
}
