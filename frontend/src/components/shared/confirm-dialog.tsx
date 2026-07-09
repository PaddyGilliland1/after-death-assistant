/*
  A small confirmation dialog for actions that deserve a pause. Focus
  trapping and escape handling come from the shadcn dialog primitives.
  The confirm action may be async; the dialog shows a pending state and
  surfaces any error without closing.
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

export interface ConfirmDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  description: string
  /** Called on confirm. Throw (or reject) to keep the dialog open with an error. */
  onConfirm: () => Promise<void> | void
  confirmLabel?: string
  cancelLabel?: string
  /** Styles the confirm button for destructive actions. */
  destructive?: boolean
}

export function ConfirmDialog({
  open,
  onOpenChange,
  title,
  description,
  onConfirm,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
}: ConfirmDialogProps) {
  const [isPending, setIsPending] = React.useState(false)
  const [error, setError] = React.useState<string | null>(null)

  function handleOpenChange(next: boolean) {
    if (isPending) return
    if (!next) setError(null)
    onOpenChange(next)
  }

  async function handleConfirm() {
    setError(null)
    setIsPending(true)
    try {
      await onConfirm()
      onOpenChange(false)
    } catch (cause) {
      setError(
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
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {error ? (
          <div
            role="alert"
            className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {error}
          </div>
        ) : null}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={isPending}
          >
            {cancelLabel}
          </Button>
          <Button
            type="button"
            variant={destructive ? "destructive" : "default"}
            onClick={handleConfirm}
            disabled={isPending}
          >
            {isPending ? "Working" : confirmLabel}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
