/*
  Archive (soft delete) dialog with a required reason. Nothing is ever
  physically deleted: the reason is stored with archived_at on the server.
  Pairs with useArchiveResource from src/lib/hooks/use-resource.ts.
*/

import * as React from "react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { isApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

export interface ArchiveDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** What is being archived, e.g. "asset" or the record's display name. */
  itemLabel: string
  /** Called with the reason on confirm. Throw (or reject) to surface an error. */
  onConfirm: (reason: string) => Promise<void> | void
  title?: string
  description?: string
}

export function ArchiveDialog({
  open,
  onOpenChange,
  itemLabel,
  onConfirm,
  title,
  description,
}: ArchiveDialogProps) {
  const [reason, setReason] = React.useState("")
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  )
  const [serverError, setServerError] = React.useState<string | null>(null)
  const [isPending, setIsPending] = React.useState(false)
  const reasonId = React.useId()
  const errorId = `${reasonId}-error`

  function handleOpenChange(next: boolean) {
    if (isPending) return
    if (!next) {
      setReason("")
      setValidationError(null)
      setServerError(null)
    }
    onOpenChange(next)
  }

  async function handleConfirm(event: React.FormEvent) {
    event.preventDefault()
    setServerError(null)

    const trimmed = reason.trim()
    if (!trimmed) {
      setValidationError("Please give a short reason for archiving.")
      return
    }
    setValidationError(null)

    setIsPending(true)
    try {
      await onConfirm(trimmed)
      handleOpenChange(false)
    } catch (cause) {
      setServerError(
        isApiError(cause)
          ? cause.message
          : "Something went wrong. Please try again.",
      )
    } finally {
      setIsPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={handleConfirm} noValidate>
          <DialogHeader>
            <DialogTitle>{title ?? `Archive this ${itemLabel}`}</DialogTitle>
            <DialogDescription>
              {description ??
                "The record will be archived, not deleted, and the reason kept with it. An administrator can restore it later."}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-1.5 py-4">
            <label htmlFor={reasonId} className="text-sm font-medium">
              Reason for archiving
            </label>
            <textarea
              id={reasonId}
              value={reason}
              onChange={(event) => {
                setReason(event.target.value)
                if (validationError) setValidationError(null)
              }}
              rows={3}
              disabled={isPending}
              aria-invalid={validationError ? true : undefined}
              aria-describedby={validationError ? errorId : undefined}
              placeholder="For example: recorded twice in error"
              className={cn(
                "flex min-h-20 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm",
                "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                "aria-invalid:border-destructive",
              )}
            />
            {validationError ? (
              <p id={errorId} className="text-sm text-destructive">
                {validationError}
              </p>
            ) : null}
          </div>

          {serverError ? (
            <div
              role="alert"
              className="mb-4 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
            >
              {serverError}
            </div>
          ) : null}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={isPending}>
              {isPending ? "Archiving" : "Archive"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
