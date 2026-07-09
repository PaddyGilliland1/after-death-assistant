/*
  Ask the knowledge assistant: a question box over POST /knowledge/qa.
  Answers render with [n] citations linked to the numbered sources list
  below; a refusal is shown calmly; a 503 means the assistant is not
  configured yet. The guidance disclaimer is always visible.
*/

import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import { MessageCircleQuestion } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { api, isApiError } from "@/lib/api"

import { type QaResponse, type QaSource } from "./knowledge-meta"
import { ExternalTextLink } from "./shared"

/** Splits an answer on [n] markers and links each to its source anchor. */
function AnswerText({
  answer,
  sources,
  anchorPrefix,
}: {
  answer: string
  sources: QaSource[]
  anchorPrefix: string
}) {
  const parts = answer.split(/(\[\d+\])/g)
  return (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">
      {parts.map((part, index) => {
        const match = /^\[(\d+)\]$/.exec(part)
        if (match) {
          const n = Number(match[1])
          const source = sources.find((candidate) => candidate.n === n)
          if (source) {
            return (
              <a
                key={index}
                href={`#${anchorPrefix}-source-${n}`}
                className="font-medium text-primary underline underline-offset-4 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                aria-label={`Citation ${n}: ${source.doc_title}`}
              >
                [{n}]
              </a>
            )
          }
        }
        return <React.Fragment key={index}>{part}</React.Fragment>
      })}
    </p>
  )
}

export function AskSection() {
  const [question, setQuestion] = React.useState("")
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)
  const textareaId = React.useId()
  const anchorPrefix = React.useId().replaceAll(":", "")

  const qa = useMutation({
    mutationFn: (asked: string) =>
      api.post<QaResponse>("/knowledge/qa", { question: asked }),
    onSuccess: () => setErrorMessage(null),
    onError: (error) => {
      if (isApiError(error) && error.status === 503) {
        setErrorMessage("The assistant is not configured yet.")
      } else {
        setErrorMessage(
          isApiError(error)
            ? error.message
            : "The question could not be answered. Please try again.",
        )
      }
    },
  })

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const trimmed = question.trim()
    if (!trimmed) return
    qa.mutate(trimmed)
  }

  const result = qa.data

  return (
    <div className="space-y-6">
      <form onSubmit={handleSubmit} className="max-w-2xl space-y-3" noValidate>
        <div className="space-y-1.5">
          <label htmlFor={textareaId} className="text-sm font-medium">
            Your question
          </label>
          <textarea
            id={textareaId}
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            rows={3}
            placeholder="For example: when is form IHT400 needed instead of IHT205?"
            className="flex min-h-20 w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring md:text-sm"
          />
        </div>
        <Button type="submit" disabled={qa.isPending || !question.trim()}>
          <MessageCircleQuestion aria-hidden="true" />
          {qa.isPending ? "Asking" : "Ask"}
        </Button>
      </form>

      {errorMessage ? (
        <p role="alert" className="text-sm text-muted-foreground">
          {errorMessage}
        </p>
      ) : null}

      {result ? (
        result.refused ? (
          <div
            role="status"
            className="max-w-2xl rounded-lg border bg-muted/30 px-4 py-3"
          >
            <p className="text-sm font-medium">
              The assistant did not answer this one.
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {result.answer ||
                "It only answers from the cached official sources, and they do not cover this question."}
            </p>
          </div>
        ) : (
          <div className="max-w-2xl space-y-4">
            <div className="rounded-lg border px-4 py-3">
              <h3 className="mb-2 text-sm font-semibold">Answer</h3>
              <AnswerText
                answer={result.answer}
                sources={result.sources}
                anchorPrefix={anchorPrefix}
              />
            </div>

            {result.sources.length > 0 ? (
              <div>
                <h3 className="mb-2 text-sm font-semibold">Sources</h3>
                <ol aria-label="Sources" className="space-y-2">
                  {result.sources.map((source) => (
                    <li
                      key={source.n}
                      id={`${anchorPrefix}-source-${source.n}`}
                      className="flex flex-wrap items-center gap-2 text-sm"
                    >
                      <span className="font-medium text-muted-foreground">
                        [{source.n}]
                      </span>
                      {source.source_url ? (
                        <ExternalTextLink href={source.source_url}>
                          {source.doc_title}
                        </ExternalTextLink>
                      ) : (
                        <span>{source.doc_title}</span>
                      )}
                      {source.form_code ? (
                        <Badge variant="secondary">{source.form_code}</Badge>
                      ) : null}
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}
          </div>
        )
      ) : null}
    </div>
  )
}
