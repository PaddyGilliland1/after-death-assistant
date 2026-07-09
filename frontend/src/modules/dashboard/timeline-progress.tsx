/*
  Timeline progress card for the dashboard: how far through the
  administration process the estate is, from GET /process/timeline.
  A labelled progress bar (not a chart) keeps it calm and accessible;
  the current step is named so the next action is always visible.
*/

import { Link } from "react-router-dom"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useResourceList } from "@/lib/hooks/use-resource"

interface TimelineStep {
  step_id: string
  order: number
  name: string
  derived_status: "done" | "current" | "upcoming"
}

export function TimelineProgress() {
  const { data, isLoading } = useResourceList<TimelineStep>("/process/timeline")

  const steps = data ?? []
  const done = steps.filter((step) => step.derived_status === "done").length
  const total = steps.length
  const current = steps.find((step) => step.derived_status === "current")
  const percent = total === 0 ? 0 : Math.round((done / total) * 100)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Process timeline</CardTitle>
        <CardDescription>
          Progress through the administration steps.{" "}
          <Link to="/timeline" className="underline underline-offset-2">
            Open the timeline
          </Link>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading ? (
          <Skeleton className="h-10 w-full" />
        ) : total === 0 ? (
          <p className="text-sm text-muted-foreground">
            Timeline steps will appear once the estate is set up.
          </p>
        ) : (
          <>
            <div
              role="progressbar"
              aria-valuenow={done}
              aria-valuemin={0}
              aria-valuemax={total}
              aria-label={`${done} of ${total} steps complete`}
              className="h-3 w-full overflow-hidden rounded-full bg-muted"
            >
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${percent}%` }}
              />
            </div>
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">
                {done} of {total}
              </span>{" "}
              steps complete ({percent}%).
              {current ? (
                <>
                  {" "}
                  Current step:{" "}
                  <span className="font-medium text-foreground">
                    {current.name}
                  </span>
                </>
              ) : null}
            </p>
          </>
        )}
      </CardContent>
    </Card>
  )
}
