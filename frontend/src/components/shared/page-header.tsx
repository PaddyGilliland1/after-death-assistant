/*
  Standard module page header: an h1, a one line purpose, and an optional
  primary action. The action only renders for roles that can write
  (executor or admin); hiding it for viewers is a courtesy, the server
  remains the authority on every write.
*/

import type * as React from "react"
import { Plus } from "lucide-react"

import { Button } from "@/components/ui/button"
import { canWrite, useMe } from "@/lib/auth"

export interface PageHeaderProps {
  title: string
  description?: string
  /** Label for the primary action button, e.g. "Add asset". */
  actionLabel?: string
  /** Called when the primary action is pressed. */
  onAction?: () => void
  /** Extra header content (filters, secondary actions). Not role gated. */
  children?: React.ReactNode
}

export function PageHeader({
  title,
  description,
  actionLabel,
  onAction,
  children,
}: PageHeaderProps) {
  const { role } = useMe()
  const showAction = Boolean(actionLabel && onAction && canWrite(role))

  return (
    <header className="mb-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
          {description ? (
            <p className="mt-2 max-w-prose text-muted-foreground">
              {description}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {children}
          {showAction ? (
            <Button type="button" onClick={onAction}>
              <Plus aria-hidden="true" />
              {actionLabel}
            </Button>
          ) : null}
        </div>
      </div>
    </header>
  )
}
