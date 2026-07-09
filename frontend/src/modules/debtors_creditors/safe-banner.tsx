/*
  The distribution guard banner, driven by
  GET /creditor-notices/safe-to-distribute. Green when every Section 27
  notice has passed its claim deadline with no open claims; amber with the
  server's reasons otherwise. This is a guard for the executor's benefit,
  never advice, and the copy says so.
*/

import { CircleCheck, TriangleAlert } from "lucide-react"

import { formatDate } from "@/components/shared/formatters"
import { Skeleton } from "@/components/ui/skeleton"
import { useResource } from "@/lib/hooks/use-resource"
import { cn } from "@/lib/utils"

import type { SafeToDistribute } from "./types"

const GUARD_COPY =
  "This is an automated guard based on the notices and claims recorded here. It is not legal or financial advice; take professional advice before distributing the estate."

export function SafeToDistributeBanner() {
  /*
    useResource builds GET /creditor-notices/safe-to-distribute and caches
    it under the /creditor-notices key, so any notice mutation refreshes
    the banner automatically.
  */
  const { data, isPending } = useResource<SafeToDistribute>(
    "/creditor-notices",
    "safe-to-distribute",
  )

  if (isPending) {
    return <Skeleton className="mb-8 h-24 w-full" aria-hidden="true" />
  }

  if (!data) {
    return (
      <p className="mb-8 text-sm text-muted-foreground" role="status">
        The distribution check is not available yet. It will appear here once
        the server is connected.
      </p>
    )
  }

  const safe = data.safe_to_distribute

  return (
    <section
      role="status"
      aria-label="Distribution check"
      className={cn(
        "mb-8 rounded-xl border p-4",
        safe
          ? "border-emerald-600/40 bg-emerald-600/10"
          : "border-amber-600/40 bg-amber-600/10",
      )}
    >
      <div className="flex items-start gap-3">
        {safe ? (
          <CircleCheck
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0 text-emerald-700 dark:text-emerald-400"
          />
        ) : (
          <TriangleAlert
            aria-hidden="true"
            className="mt-0.5 size-5 shrink-0 text-amber-700 dark:text-amber-400"
          />
        )}
        <div className="space-y-2">
          <p className="font-semibold">
            {safe ? "Safe to distribute" : "Not yet safe to distribute"}
            <span className="ml-2 text-xs font-normal text-muted-foreground">
              Checked on {formatDate(data.checked_on)}
            </span>
          </p>
          {data.reasons.length > 0 ? (
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {data.reasons.map((reason) => (
                <li key={reason}>{reason}</li>
              ))}
            </ul>
          ) : null}
          <p className="text-xs text-muted-foreground">{GUARD_COPY}</p>
        </div>
      </div>
    </section>
  )
}
