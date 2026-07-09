/*
  New-draft actions: ask the assistant for an IHT400 form draft, a
  notification letter draft (contact picker plus purpose) or task
  suggestions. Each action posts to its /agents endpoint and reports its
  own outcome inline. A 503 from an LLM-dependent endpoint renders the
  calm "not configured" line; the buttons stay enabled because the
  deterministic form drafting works without a model.
*/

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileText, ListPlus, Mail } from "lucide-react"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { api, isApiError } from "@/lib/api"
import { useResourceList } from "@/lib/hooks/use-resource"
import type { Contact } from "@/lib/types"

import { ASSISTANT_NOT_CONFIGURED } from "./draft-meta"

const DRAFTS_PATH = "/agents/drafts"

/*
  The drafting endpoints return the drafted content plus its
  approval-pending reference (draft_id, approval_id). The page's list
  refetch is what surfaces the new draft; only the ids matter here.
*/
interface DraftResponse {
  draft_id?: string
  approval_id?: string
  [key: string]: unknown
}

const selectClassName =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"

function errorText(error: unknown, fallback: string): string {
  if (isApiError(error)) {
    if (error.status === 503) return ASSISTANT_NOT_CONFIGURED
    return error.message
  }
  return fallback
}

interface LetterDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onDrafted: () => void
}

function LetterDialog({ open, onOpenChange, onDrafted }: LetterDialogProps) {
  const { data: contacts } = useResourceList<Contact>("/contacts", {
    enabled: open,
  })
  const [contactId, setContactId] = React.useState("")
  const [purpose, setPurpose] = React.useState("")
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  )
  const [serverError, setServerError] = React.useState<string | null>(null)
  const contactSelectId = React.useId()
  const purposeId = React.useId()

  const draftLetter = useMutation({
    mutationFn: (input: { contact_id: string; purpose: string }) =>
      api.post<DraftResponse>("/agents/draft-letter", input),
  })

  function reset() {
    setContactId("")
    setPurpose("")
    setValidationError(null)
    setServerError(null)
  }

  function handleOpenChange(next: boolean) {
    if (draftLetter.isPending) return
    if (!next) reset()
    onOpenChange(next)
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setServerError(null)
    if (!contactId) {
      setValidationError("Please choose who the letter is for.")
      return
    }
    if (!purpose.trim()) {
      setValidationError("Please say what the letter is for.")
      return
    }
    setValidationError(null)
    try {
      await draftLetter.mutateAsync({
        contact_id: contactId,
        purpose: purpose.trim(),
      })
      reset()
      onOpenChange(false)
      onDrafted()
    } catch (cause) {
      setServerError(
        errorText(cause, "The letter could not be drafted. Please try again."),
      )
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Draft a letter</DialogTitle>
            <DialogDescription>
              The assistant drafts the letter for your review. Nothing is
              sent by this application.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-1.5">
              <label htmlFor={contactSelectId} className="text-sm font-medium">
                Contact
              </label>
              <select
                id={contactSelectId}
                value={contactId}
                disabled={draftLetter.isPending}
                onChange={(event) => setContactId(event.target.value)}
                className={selectClassName}
              >
                <option value="">Choose a contact</option>
                {(contacts ?? []).map((contact) => (
                  <option key={contact.id} value={contact.id}>
                    {contact.name}
                    {contact.org ? ` (${contact.org})` : ""}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label htmlFor={purposeId} className="text-sm font-medium">
                Purpose
              </label>
              <Input
                id={purposeId}
                value={purpose}
                disabled={draftLetter.isPending}
                onChange={(event) => setPurpose(event.target.value)}
                placeholder="For example: notify of the death and request account closure"
              />
            </div>

            {validationError ? (
              <p role="alert" className="text-sm text-destructive">
                {validationError}
              </p>
            ) : null}
            {serverError ? (
              <div
                role="alert"
                className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
              >
                {serverError}
              </div>
            ) : null}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={draftLetter.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={draftLetter.isPending}>
              {draftLetter.isPending ? "Drafting" : "Draft letter"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

export function NewDraftActions() {
  const queryClient = useQueryClient()
  const [letterOpen, setLetterOpen] = React.useState(false)
  const [message, setMessage] = React.useState<string | null>(null)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)

  async function announceDraft(what: string) {
    setErrorMessage(null)
    setMessage(`${what} It is waiting for your review below.`)
    await queryClient.invalidateQueries({ queryKey: [DRAFTS_PATH] })
  }

  /*
    POST /agents/draft-form with no form_code drafts the IHT400 plus
    every required schedule (the deterministic pack; no model needed).
  */
  const draftForm = useMutation({
    mutationFn: () => api.post<DraftResponse>("/agents/draft-form", {}),
    onSuccess: () =>
      announceDraft("The assistant has drafted the IHT400 pack."),
    onError: (error) => {
      setMessage(null)
      setErrorMessage(
        errorText(error, "The form could not be drafted. Please try again."),
      )
    },
  })

  const suggestTasks = useMutation({
    mutationFn: () => api.post<DraftResponse>("/agents/suggest-tasks"),
    onSuccess: () =>
      announceDraft("The assistant has drafted task suggestions."),
    onError: (error) => {
      setMessage(null)
      setErrorMessage(
        errorText(
          error,
          "Task suggestions could not be produced. Please try again.",
        ),
      )
    },
  })

  return (
    <div className="mb-6 space-y-3">
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => draftForm.mutate()}
          disabled={draftForm.isPending}
        >
          <FileText aria-hidden="true" />
          {draftForm.isPending ? "Drafting IHT400" : "Draft IHT400"}
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => setLetterOpen(true)}
        >
          <Mail aria-hidden="true" />
          Draft letter
        </Button>
        <Button
          type="button"
          variant="outline"
          onClick={() => suggestTasks.mutate()}
          disabled={suggestTasks.isPending}
        >
          <ListPlus aria-hidden="true" />
          {suggestTasks.isPending ? "Suggesting tasks" : "Suggest tasks"}
        </Button>
      </div>

      {message ? (
        <p role="status" className="text-sm text-muted-foreground">
          {message}
        </p>
      ) : null}
      {errorMessage ? (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage}
        </p>
      ) : null}

      <LetterDialog
        open={letterOpen}
        onOpenChange={setLetterOpen}
        onDrafted={() => {
          void announceDraft("The assistant has drafted the letter.")
        }}
      />
    </div>
  )
}
