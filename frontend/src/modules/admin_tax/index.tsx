/*
  Administration tax module: one card per tax year with the income total,
  the complex estate flag (and what triggered it), the ISA exemption end
  date, and the year's capital gains disposals with their derived 60 day
  reporting deadlines and basis citations. Writers can create and edit
  year records and disposals.
*/

import * as React from "react"
import { CalendarClock } from "lucide-react"

import { formatDate, formatMoney } from "@/components/shared/formatters"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { ApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import {
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"

import {
  ADMIN_TAX_PATH,
  complexReasons,
  toDisposalEntry,
  toYearPayload,
  type AdminTaxYear,
  type Cgt60DayDeadline,
  type DisposalFormValues,
  type YearFormValues,
} from "./admin-tax-meta"
import { DisposalForm, YearForm } from "./forms"
import { useEstateId } from "./use-estate-id"

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

/** The derived deadline matching a disposal, paired by disposal date. */
function deadlineFor(
  year: AdminTaxYear,
  disposalDate: string | null | undefined,
): Cgt60DayDeadline | undefined {
  if (!disposalDate) return undefined
  return (year.cgt_60day_deadlines ?? []).find(
    (entry) => entry.disposal_date === disposalDate,
  )
}

interface DisposalsTableProps {
  year: AdminTaxYear
  writer: boolean
  onEditDisposal: (index: number) => void
}

function DisposalsTable({ year, writer, onEditDisposal }: DisposalsTableProps) {
  const today = todayIso()

  if (year.cgt_disposals.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        No disposals recorded for this year yet.
      </p>
    )
  }

  return (
    <Table aria-label={`Disposals in ${year.tax_year}`}>
      <TableHeader>
        <TableRow>
          <TableHead>Description</TableHead>
          <TableHead>Disposal date</TableHead>
          <TableHead className="text-right">Proceeds</TableHead>
          <TableHead className="text-right">Gain</TableHead>
          <TableHead>60 day deadline</TableHead>
          {writer ? <TableHead className="sr-only">Actions</TableHead> : null}
        </TableRow>
      </TableHeader>
      <TableBody>
        {year.cgt_disposals.map((disposal, index) => {
          const deadline = deadlineFor(year, disposal.disposal_date)
          const overdue = Boolean(
            deadline?.deadline && deadline.deadline < today,
          )
          return (
            <TableRow key={index}>
              <TableCell>
                {typeof disposal.description === "string" &&
                disposal.description
                  ? disposal.description
                  : "Disposal"}
              </TableCell>
              <TableCell>
                {formatDate(disposal.disposal_date ?? null) || (
                  <span aria-hidden="true">&ndash;</span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatMoney(disposal.proceeds ?? null) || (
                  <span aria-hidden="true">&ndash;</span>
                )}
              </TableCell>
              <TableCell className="text-right tabular-nums">
                {formatMoney(disposal.gain ?? null) || (
                  <span aria-hidden="true">&ndash;</span>
                )}
              </TableCell>
              <TableCell>
                {deadline ? (
                  <span className="inline-flex flex-wrap items-center gap-2">
                    <span>{formatDate(deadline.deadline)}</span>
                    {overdue ? (
                      <Badge variant="destructive">Overdue</Badge>
                    ) : null}
                    <span className="text-xs text-muted-foreground">
                      {deadline.basis}
                    </span>
                  </span>
                ) : (
                  <span aria-hidden="true">&ndash;</span>
                )}
              </TableCell>
              {writer ? (
                <TableCell>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => onEditDisposal(index)}
                  >
                    Edit
                    <span className="sr-only">
                      {" "}
                      disposal{" "}
                      {typeof disposal.description === "string"
                        ? disposal.description
                        : String(index + 1)}
                    </span>
                  </Button>
                </TableCell>
              ) : null}
            </TableRow>
          )
        })}
      </TableBody>
    </Table>
  )
}

interface YearCardProps {
  year: AdminTaxYear
  writer: boolean
  onEditYear: () => void
  onAddDisposal: () => void
  onEditDisposal: (index: number) => void
}

function YearCard({
  year,
  writer,
  onEditYear,
  onAddDisposal,
  onEditDisposal,
}: YearCardProps) {
  const reasons = complexReasons(year)

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex flex-wrap items-center gap-2 text-base">
          Tax year {year.tax_year}
          {year.estate_complex ? (
            <Badge variant="outline">Complex estate</Badge>
          ) : null}
        </CardTitle>
        {year.estate_complex ? (
          <CardDescription>
            {reasons.length > 0
              ? `Marked complex because: ${reasons.join("; ")}.`
              : "The estate meets HMRC's complex estate criteria for this year."}
          </CardDescription>
        ) : null}
      </CardHeader>
      <CardContent className="space-y-4">
        <dl className="grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="text-sm text-muted-foreground">Income total</dt>
            <dd className="text-lg font-medium tabular-nums">
              {formatMoney(year.income_total, "Not yet recorded")}
            </dd>
          </div>
          <div>
            <dt className="flex items-center gap-1.5 text-sm text-muted-foreground">
              <CalendarClock aria-hidden="true" className="size-3.5" />
              ISA exemption ends
            </dt>
            <dd className="text-lg font-medium">
              {formatDate(year.isa_exemption_end, "Not yet recorded")}
            </dd>
          </div>
        </dl>

        <div>
          <h3 className="mb-2 text-sm font-medium">Capital gains disposals</h3>
          <DisposalsTable
            year={year}
            writer={writer}
            onEditDisposal={onEditDisposal}
          />
          <p className="mt-2 text-xs text-muted-foreground">
            Disposals of UK residential property must be reported and any
            capital gains tax paid within 60 days of completion.
          </p>
        </div>

        {writer ? (
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onEditYear}
            >
              Edit year
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={onAddDisposal}
            >
              Add disposal
            </Button>
          </div>
        ) : null}
      </CardContent>
    </Card>
  )
}

export default function AdminTaxPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const estateId = useEstateId()

  const { data, isPending } = useResourceList<AdminTaxYear>(ADMIN_TAX_PATH)
  const create = useCreateResource<AdminTaxYear>(ADMIN_TAX_PATH)
  const update = useUpdateResource<AdminTaxYear>(ADMIN_TAX_PATH)

  const [createOpen, setCreateOpen] = React.useState(false)
  const [editYearId, setEditYearId] = React.useState<string | null>(null)
  const [disposalTarget, setDisposalTarget] = React.useState<{
    yearId: string
    index: number | null
  } | null>(null)

  const years = React.useMemo(() => {
    const list = data ?? []
    return [...list].sort((a, b) => b.tax_year.localeCompare(a.tax_year))
  }, [data])

  const editYear = years.find((year) => year.id === editYearId)
  const disposalYear = years.find(
    (year) => year.id === disposalTarget?.yearId,
  )
  const editingDisposal =
    disposalYear && disposalTarget && disposalTarget.index !== null
      ? disposalYear.cgt_disposals[disposalTarget.index]
      : undefined

  async function handleCreateYear(values: YearFormValues) {
    if (!estateId) {
      throw new ApiError(
        0,
        "The estate details are still loading. Please try again in a moment.",
      )
    }
    await create.mutateAsync({
      estate_id: estateId,
      ...toYearPayload(values),
      cgt_disposals: [],
    })
    setCreateOpen(false)
  }

  async function handleEditYear(values: YearFormValues) {
    if (!editYear) return
    await update.mutateAsync({ id: editYear.id, data: toYearPayload(values) })
    setEditYearId(null)
  }

  async function handleSaveDisposal(values: DisposalFormValues) {
    if (!disposalYear || !disposalTarget) return
    const entry = toDisposalEntry(values)
    const next =
      disposalTarget.index === null
        ? [...disposalYear.cgt_disposals, entry]
        : disposalYear.cgt_disposals.map((existing, index) =>
            index === disposalTarget.index ? entry : existing,
          )
    await update.mutateAsync({
      id: disposalYear.id,
      data: { cgt_disposals: next },
    })
    setDisposalTarget(null)
  }

  return (
    <section aria-label="Administration tax">
      <PageHeader
        title="Administration tax"
        description="Income tax and capital gains during the administration period, including the 60 day rule for UK residential property."
        actionLabel="Add tax year"
        onAction={() => setCreateOpen(true)}
      />

      {isPending ? (
        <div className="space-y-4" aria-hidden="true">
          <Skeleton className="h-40 w-full rounded-xl" />
          <Skeleton className="h-40 w-full rounded-xl" />
        </div>
      ) : years.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center">
            <p className="font-medium">
              No administration period tax recorded yet.
            </p>
            <p className="mx-auto mt-2 max-w-sm text-sm text-muted-foreground">
              Add a tax year to track estate income, capital gains disposals
              and their reporting deadlines.
            </p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-6">
          {years.map((year) => (
            <YearCard
              key={year.id}
              year={year}
              writer={writer}
              onEditYear={() => setEditYearId(year.id)}
              onAddDisposal={() =>
                setDisposalTarget({ yearId: year.id, index: null })
              }
              onEditDisposal={(index) =>
                setDisposalTarget({ yearId: year.id, index })
              }
            />
          ))}
        </div>
      )}

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add tax year</DialogTitle>
            <DialogDescription>
              A tax year of the administration period.
            </DialogDescription>
          </DialogHeader>
          <YearForm
            onSubmit={handleCreateYear}
            onCancel={() => setCreateOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {editYear ? (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setEditYearId(null)
          }}
        >
          <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>Edit tax year {editYear.tax_year}</DialogTitle>
              <DialogDescription>
                Changes are saved to the year record.
              </DialogDescription>
            </DialogHeader>
            <YearForm
              year={editYear}
              onSubmit={handleEditYear}
              onCancel={() => setEditYearId(null)}
            />
          </DialogContent>
        </Dialog>
      ) : null}

      {disposalYear ? (
        <Dialog
          open
          onOpenChange={(open) => {
            if (!open) setDisposalTarget(null)
          }}
        >
          <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
            <DialogHeader>
              <DialogTitle>
                {editingDisposal ? "Edit disposal" : "Add disposal"}
              </DialogTitle>
              <DialogDescription>
                A capital gains disposal in tax year {disposalYear.tax_year}.
                The 60 day reporting deadline is derived by the server.
              </DialogDescription>
            </DialogHeader>
            <DisposalForm
              disposal={editingDisposal}
              onSubmit={handleSaveDisposal}
              onCancel={() => setDisposalTarget(null)}
            />
          </DialogContent>
        </Dialog>
      ) : null}
    </section>
  )
}
