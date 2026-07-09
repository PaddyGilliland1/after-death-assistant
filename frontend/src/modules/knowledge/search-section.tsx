/*
  Knowledge search: a labelled query box over GET /knowledge/search?q=,
  with hits shown as the matched chunk, the document title, its form code
  badge, a source link and the licence attribution line.
*/

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { Search } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"

import type { KnowledgeSearchHit } from "./knowledge-meta"
import { ExternalTextLink, LicenceLine } from "./shared"

export function SearchSection() {
  const [query, setQuery] = React.useState("")
  const [term, setTerm] = React.useState("")
  const inputId = React.useId()

  const results = useQuery({
    queryKey: ["/knowledge", "search", term],
    enabled: term.length > 0,
    queryFn: async (): Promise<KnowledgeSearchHit[] | null> => {
      try {
        return await api.get<KnowledgeSearchHit[]>(
          `/knowledge/search?q=${encodeURIComponent(term)}`,
        )
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
  })

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setTerm(query.trim())
  }

  const hits = results.data ?? []

  return (
    <div className="space-y-6">
      <form
        onSubmit={handleSubmit}
        className="flex max-w-xl items-end gap-2"
        noValidate
      >
        <div className="flex-1 space-y-1.5">
          <label htmlFor={inputId} className="text-sm font-medium">
            Search the library
          </label>
          <Input
            id={inputId}
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="For example: IHT400, loss on sale, excepted estate"
          />
        </div>
        <Button type="submit" disabled={!query.trim()}>
          <Search aria-hidden="true" />
          Search
        </Button>
      </form>

      {term && results.isPending ? (
        <div className="space-y-3" aria-hidden="true">
          <Skeleton className="h-20 w-full rounded-lg" />
          <Skeleton className="h-20 w-full rounded-lg" />
        </div>
      ) : null}

      {results.isError ? (
        <p role="alert" className="text-sm text-destructive">
          The search could not be completed. Please try again.
        </p>
      ) : null}

      {term && results.isSuccess ? (
        results.data === null ? (
          <p className="text-sm text-muted-foreground">
            Search is not available yet. It will work once guidance has been
            ingested.
          </p>
        ) : hits.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No matches for &ldquo;{term}&rdquo; in the cached guidance.
          </p>
        ) : (
          <ol aria-label="Search results" className="space-y-4">
            {hits.map((hit) => (
              <li
                key={`${hit.doc_id}-${hit.chunk_index}`}
                className="rounded-lg border px-4 py-3"
              >
                <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                  {hit.doc_title}
                  {hit.form_code ? (
                    <Badge variant="secondary">{hit.form_code}</Badge>
                  ) : null}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  {hit.chunk_text}
                </p>
                <div className="mt-2 space-y-1 text-sm">
                  {hit.source_url ? (
                    <ExternalTextLink href={hit.source_url}>
                      View source
                    </ExternalTextLink>
                  ) : null}
                  <LicenceLine
                    licence={hit.licence}
                    fetchDate={hit.fetch_date}
                  />
                </div>
              </li>
            ))}
          </ol>
        )
      ) : null}
    </div>
  )
}
