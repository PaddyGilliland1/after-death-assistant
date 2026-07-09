/*
  IHT workbench v1: the latest assessment from GET /iht/assessment as
  stat cards with filing badges, a write-gated Recompute action
  (POST /iht/recompute), the required schedules from GET /iht/schedules,
  and the estate settings dialog (GET/PUT /estate).

  Every figure shown comes from the deterministic engine or the estate
  row and is displayed exactly as returned; the only client-side logic is
  the taper indicator, a comparison of two returned figures.
*/

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { ListPlus, RefreshCw, Settings2 } from "lucide-react"
import { toast } from "sonner"

import { formatDate } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
import { StatCard } from "@/components/shared/stat-card"
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

import { EstateSettingsDialog } from "./estate-settings-dialog"
import { IhtExportActions } from "./export-actions"
import { formatMoneyExact, formatRate } from "./money"
import {
  useEstateSettings,
  useIhtAssessment,
  useIhtSchedules,
  useRecomputeIht,
  type IhtAssessment,
} from "./use-iht"

/** The engine input's net estate value, when the snapshot carries one. */
function netValueOf(assessment: IhtAssessment): string | null {
  const raw = assessment.inputs["net_value"]
  if (typeof raw === "string" || typeof raw === "number") return String(raw)
  return null
}

function AssessmentBadges({
  assessment,
  taperApplied,
}: {
  assessment: IhtAssessment
  taperApplied: boolean
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {assessment.must_file_iht400 ? (
        <Badge>IHT400 required</Badge>
      ) : (
        <Badge variant="secondary">IHT400 not required</Badge>
      )}
      {assessment.is_excepted ? (
        <Badge variant="secondary">Excepted estate</Badge>
      ) : (
        <Badge variant="outline">Not an excepted estate</Badge>
      )}
      {taperApplied ? (
        <Badge variant="outline">RNRB taper applied</Badge>
      ) : null}
      <span className="text-xs text-muted-foreground">
        Assessed {formatDate(assessment.created_at)} using constants{" "}
        {assessment.constants_version}
      </span>
    </div>
  )
}

function seedResultMessage(result: unknown): string {
  const shaped = result as { created?: string[]; skipped?: string[] }
  const created = shaped.created?.length ?? 0
  const skipped = shaped.skipped?.length ?? 0
  if (created === 0) return "All required schedules already have tasks."
  const plural = created === 1 ? "task" : "tasks"
  return skipped > 0
    ? `Added ${created} schedule ${plural}; ${skipped} already existed.`
    : `Added ${created} schedule ${plural}.`
}

function SchedulesCard({ writable }: { writable: boolean }) {
  const { data, isPending, isError } = useIhtSchedules()
  const queryClient = useQueryClient()

  const seed = useMutation({
    mutationFn: () => api.post<unknown>("/iht/schedules/seed-tasks"),
    onSuccess: async (result) => {
      toast.success(seedResultMessage(result))
      await queryClient.invalidateQueries({ queryKey: ["/tasks"] })
    },
    onError: (error) => {
      toast.error(
        isApiError(error)
          ? error.message
          : "The schedule tasks could not be created. Please try again.",
      )
    },
  })

  const hasSchedules = Boolean(data && data.schedules.length > 0)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Required schedules</CardTitle>
        <CardDescription>
          Supplementary schedules the latest assessment requires, with the
          reason for each.
        </CardDescription>
        {writable && hasSchedules ? (
          <Button
            variant="outline"
            size="sm"
            onClick={() => seed.mutate()}
            disabled={seed.isPending}
            className="w-fit"
          >
            <ListPlus aria-hidden="true" />
            {seed.isPending ? "Adding schedule tasks" : "Add schedule tasks"}
          </Button>
        ) : null}
      </CardHeader>
      <CardContent>
        {isPending ? (
          <div className="space-y-3" aria-hidden="true">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-2/3" />
          </div>
        ) : data === null || isError ? (
          <p className="text-sm text-muted-foreground">
            Schedules will appear here once an assessment has been produced.
          </p>
        ) : data.schedules.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            The latest assessment requires no supplementary schedules.
          </p>
        ) : (
          <ul className="divide-y">
            {data.schedules.map((schedule) => (
              <li key={schedule.code} className="flex gap-4 py-3 text-sm">
                <span className="w-20 shrink-0 font-medium tabular-nums">
                  {schedule.code}
                </span>
                <span className="text-muted-foreground">
                  {schedule.reason}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  )
}

export default function IhtPage() {
  const { role } = useMe()
  const writable = canWrite(role)

  const assessmentQuery = useIhtAssessment()
  const settingsQuery = useEstateSettings()
  const recompute = useRecomputeIht()

  const [settingsOpen, setSettingsOpen] = React.useState(false)

  const assessment = assessmentQuery.data
  const settings = settingsQuery.data

  const netValue = assessment ? netValueOf(assessment) : null

  // Indicator only: a comparison of two returned figures, no arithmetic.
  const taperApplied = Boolean(
    assessment &&
      netValue !== null &&
      settings?.taper_threshold != null &&
      Number(netValue) > Number(settings.taper_threshold),
  )

  function handleRecompute() {
    recompute.mutate(undefined, {
      onSuccess: () => toast.success("Assessment recomputed"),
      onError: (error) =>
        toast.error(
          isApiError(error)
            ? error.message
            : "The assessment could not be recomputed. Please try again.",
        ),
    })
  }

  return (
    <section aria-label="Inheritance tax">
      <PageHeader
        title="Inheritance tax"
        description="The current assessment, the filing route and the schedules required."
      >
        <IhtExportActions />
        {writable ? (
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => setSettingsOpen(true)}
              disabled={!settings}
            >
              <Settings2 aria-hidden="true" />
              Estate settings
            </Button>
            <Button
              type="button"
              onClick={handleRecompute}
              disabled={recompute.isPending}
            >
              <RefreshCw aria-hidden="true" />
              {recompute.isPending ? "Recomputing" : "Recompute"}
            </Button>
          </>
        ) : null}
      </PageHeader>

      <p
        role="note"
        className="mb-6 rounded-md border bg-muted/50 px-4 py-3 text-sm text-muted-foreground"
      >
        Figures are computed by the deterministic engine. This tool informs
        and drafts; it is not tax advice.
      </p>

      <div className="space-y-8">
        {assessmentQuery.isPending ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {["Net value", "Allowance", "Taxable", "Rate", "Tax due"].map(
              (label) => (
                <StatCard key={label} label={label} value={null} isLoading />
              ),
            )}
          </div>
        ) : !assessment || assessmentQuery.isError ? (
          <p role="status" className="text-sm text-muted-foreground">
            No assessment has been produced yet.
            {writable
              ? " Choose Recompute to produce the first assessment from the estate records."
              : " It will appear here once an executor recomputes the estate."}
          </p>
        ) : (
          <>
            <AssessmentBadges
              assessment={assessment}
              taperApplied={taperApplied}
            />
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <StatCard
                label="Net value"
                value={netValue ? formatMoneyExact(netValue) || null : null}
                description="The estate value the engine assessed"
              />
              <StatCard
                label="Allowance"
                value={formatMoneyExact(assessment.allowance) || null}
                description={`Nil rate band ${formatMoneyExact(assessment.nrb)} plus residence band ${formatMoneyExact(assessment.rnrb)}`}
              />
              <StatCard
                label="Taxable"
                value={formatMoneyExact(assessment.taxable) || null}
                description="Net value less exemptions and allowance"
              />
              <StatCard
                label="Rate"
                value={formatRate(assessment.rate) || null}
                description="36% applies when at least 10% of the estate goes to charity"
              />
              <StatCard
                label="Tax due"
                value={formatMoneyExact(assessment.tax) || null}
                description="From the latest assessment snapshot"
              />
            </div>
          </>
        )}

        <SchedulesCard writable={writable} />
      </div>

      {settings ? (
        <EstateSettingsDialog
          settings={settings}
          open={settingsOpen}
          onOpenChange={setSettingsOpen}
        />
      ) : null}
    </section>
  )
}
