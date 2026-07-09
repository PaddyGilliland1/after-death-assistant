/*
  A single dashboard statistic: label, value, supporting line. Handles
  loading (skeleton) and missing values ("Not yet available") so callers
  can pass API data straight through.
*/

import type * as React from "react"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"

export interface StatCardProps {
  /** Short label above the value, e.g. "Gross estate". */
  label: string
  /** Formatted value. Pass null or undefined to show "Not yet available". */
  value: React.ReactNode | null | undefined
  /** Supporting copy under the value. */
  description?: string
  /** Shows a skeleton in place of the value. */
  isLoading?: boolean
}

export function StatCard({
  label,
  value,
  description,
  isLoading = false,
}: StatCardProps) {
  const hasValue = value !== null && value !== undefined && value !== ""

  return (
    <Card>
      <CardHeader>
        <CardDescription>{label}</CardDescription>
        <CardTitle className="text-2xl tabular-nums">
          {isLoading ? (
            <Skeleton className="h-8 w-28" aria-hidden="true" />
          ) : hasValue ? (
            value
          ) : (
            <span className="text-base font-normal text-muted-foreground">
              Not yet available
            </span>
          )}
        </CardTitle>
      </CardHeader>
      {description ? (
        <CardContent>
          <p className="text-xs text-muted-foreground">{description}</p>
        </CardContent>
      ) : null}
    </Card>
  )
}
