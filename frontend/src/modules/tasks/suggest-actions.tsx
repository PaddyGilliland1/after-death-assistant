/*
  Suggested next actions for the task list: a write-gated button that
  asks the assistant for task suggestions (POST /agents/suggest-tasks)
  and shows the returned draft inline. Suggestions become tasks only
  through the drafts approval flow, so the block links to /drafts rather
  than creating anything itself. A 503 renders the calm "not configured"
  line.
*/

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Sparkles } from "lucide-react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import {
  ASSISTANT_NOT_CONFIGURED,
  suggestionsOf,
} from "@/modules/drafts/draft-meta"

/* SuggestTasksResponse: the suggestions plus the approval reference. */
interface SuggestTasksResponse {
  draft_id?: string
  approval_id?: string
  suggestions?: unknown[]
  [key: string]: unknown
}

export function SuggestActions() {
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)

  const suggest = useMutation({
    mutationFn: () =>
      api.post<SuggestTasksResponse>("/agents/suggest-tasks"),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ["/agents/drafts"] })
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 503) {
        setErrorMessage(ASSISTANT_NOT_CONFIGURED)
      } else {
        setErrorMessage(
          isApiError(error)
            ? error.message
            : "Task suggestions could not be produced. Please try again.",
        )
      }
    },
  })

  if (!writer) return null

  const draft = suggest.data
  const suggestions = draft ? suggestionsOf(draft) : []

  return (
    <section aria-label="Suggested next actions" className="mb-6">
      <Button
        type="button"
        variant="outline"
        onClick={() => suggest.mutate()}
        disabled={suggest.isPending}
      >
        <Sparkles aria-hidden="true" />
        {suggest.isPending ? "Suggesting" : "Suggest next actions"}
      </Button>

      {errorMessage ? (
        <p role="alert" className="mt-3 text-sm text-muted-foreground">
          {errorMessage}
        </p>
      ) : null}

      {draft && !errorMessage ? (
        <div className="mt-3 rounded-md border bg-muted/30 px-4 py-3">
          <p className="text-sm font-medium">The assistant suggests:</p>
          {suggestions.length === 0 ? (
            <p className="mt-1 text-sm text-muted-foreground">
              No new actions to suggest right now.
            </p>
          ) : (
            <ul
              aria-label="Suggested tasks"
              className="mt-2 list-disc space-y-1 pl-5 text-sm"
            >
              {suggestions.map((suggestion, index) => (
                <li key={index}>
                  <span className="font-medium">{suggestion.title}</span>
                  {suggestion.description ? (
                    <span className="text-muted-foreground">
                      {" "}
                      {suggestion.description}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-sm text-muted-foreground">
            These are drafts, not tasks yet. Review and approve them on the{" "}
            <Link
              to="/drafts"
              className="font-medium underline underline-offset-4 hover:text-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              Drafts page
            </Link>{" "}
            to add them to the task list.
          </p>
        </div>
      ) : null}
    </section>
  )
}
