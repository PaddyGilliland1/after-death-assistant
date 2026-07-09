/*
  Knowledge library: the cached documents from GET /knowledge/docs as a
  DataTable, a detail dialog with the metadata and the extracted text in
  a scrollable pane, and an admin only ingest action with a per-source
  result list.
*/

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { DownloadCloud } from "lucide-react"

import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Skeleton } from "@/components/ui/skeleton"
import { api, isApiError } from "@/lib/api"
import { useResource, useResourceList } from "@/lib/hooks/use-resource"

import {
  docTitle,
  ingestResults,
  ingestSourceLabel,
  ingestSourceStatus,
  isOgl,
  type KnowledgeDoc,
} from "./knowledge-meta"
import { ExternalTextLink, LicenceLine } from "./shared"

const columns: DataTableColumn<KnowledgeDoc>[] = [
  { key: "title", header: "Title", value: (row) => docTitle(row) },
  {
    key: "form_code",
    header: "Form",
    value: (row) => row.form_code ?? null,
    render: (row) =>
      row.form_code ? (
        <Badge variant="secondary">{row.form_code}</Badge>
      ) : (
        <span aria-hidden="true">&ndash;</span>
      ),
  },
  {
    key: "licence",
    header: "Licence",
    value: (row) => row.licence ?? null,
    render: (row) =>
      row.licence ? (
        isOgl(row.licence) ? (
          <Badge variant="outline">OGL</Badge>
        ) : (
          <span>{row.licence}</span>
        )
      ) : (
        <span aria-hidden="true">&ndash;</span>
      ),
  },
  {
    key: "fetch_date",
    header: "Fetched",
    value: (row) => row.fetch_date ?? null,
    kind: "date",
  },
]

function IngestPanel() {
  const queryClient = useQueryClient()
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)

  const ingest = useMutation({
    // The endpoint takes an IngestRequest body; {} means "all sources".
    mutationFn: () => api.post<unknown>("/knowledge/ingest", {}),
    onSuccess: async () => {
      setErrorMessage(null)
      await queryClient.invalidateQueries({ queryKey: ["/knowledge/docs"] })
    },
    onError: (error) => {
      setErrorMessage(
        isApiError(error)
          ? error.message
          : "The sources could not be ingested. Please try again.",
      )
    },
  })

  const results = ingest.isSuccess ? ingestResults(ingest.data) : []

  return (
    <div className="space-y-3 rounded-lg border px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">Ingest official sources</p>
          <p className="text-xs text-muted-foreground">
            Fetches and caches the configured official guidance. Admin only.
          </p>
        </div>
        <Button
          type="button"
          variant="outline"
          onClick={() => ingest.mutate()}
          disabled={ingest.isPending}
        >
          <DownloadCloud aria-hidden="true" />
          {ingest.isPending ? "Ingesting" : "Ingest sources"}
        </Button>
      </div>

      {errorMessage ? (
        <p role="alert" className="text-sm text-destructive">
          {errorMessage}
        </p>
      ) : null}

      {ingest.isSuccess ? (
        results.length === 0 ? (
          <p role="status" className="text-sm text-muted-foreground">
            Ingest completed.
          </p>
        ) : (
          <ul aria-label="Ingest results" className="space-y-1 text-sm">
            {results.map((result, index) => {
              const status = ingestSourceStatus(result)
              const detail =
                typeof result.detail === "string" && result.detail
                  ? result.detail
                  : typeof result.error === "string" && result.error
                    ? result.error
                    : null
              return (
                <li
                  key={index}
                  className="flex flex-wrap items-center gap-2 border-b pb-1 last:border-b-0 last:pb-0"
                >
                  <span>{ingestSourceLabel(result)}</span>
                  {status ? (
                    <Badge
                      variant={
                        status === "failed" || status === "error"
                          ? "destructive"
                          : "secondary"
                      }
                    >
                      {status}
                    </Badge>
                  ) : null}
                  {detail ? (
                    <span className="text-xs text-muted-foreground">
                      {detail}
                    </span>
                  ) : null}
                </li>
              )
            })}
          </ul>
        )
      ) : null}
    </div>
  )
}

export function LibrarySection({ isAdmin }: { isAdmin: boolean }) {
  const { data, isPending } = useResourceList<KnowledgeDoc>("/knowledge/docs")
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const detail = useResource<KnowledgeDoc>("/knowledge/docs", selectedId)

  const docs = React.useMemo(() => data ?? [], [data])
  const selected = detail.data

  return (
    <div className="space-y-6">
      {isAdmin ? <IngestPanel /> : null}

      <DataTable
        columns={columns}
        rows={docs}
        rowKey={(row) => row.id}
        isLoading={isPending}
        label="Cached documents"
        filterLabel="Filter documents"
        emptyTitle="No guidance has been ingested yet."
        emptyMessage="Cached official documents will appear here once they are ingested."
        onRowClick={(row) => setSelectedId(row.id)}
      />

      <Dialog
        open={Boolean(selectedId)}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null)
        }}
      >
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
          {detail.isPending && !selected ? (
            <>
              <DialogHeader>
                <DialogTitle className="sr-only">Loading document</DialogTitle>
                <DialogDescription className="sr-only">
                  The document is loading.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-3 py-4" aria-hidden="true">
                <Skeleton className="h-6 w-2/3" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-40 w-full" />
              </div>
            </>
          ) : selected ? (
            <>
              <DialogHeader>
                <DialogTitle className="flex flex-wrap items-center gap-2">
                  {docTitle(selected)}
                  {selected.form_code ? (
                    <Badge variant="secondary">{selected.form_code}</Badge>
                  ) : null}
                </DialogTitle>
                <DialogDescription>
                  A cached copy of the official document.
                </DialogDescription>
              </DialogHeader>

              <div className="space-y-2 text-sm">
                {selected.source_url ? (
                  <ExternalTextLink href={selected.source_url}>
                    View the source
                  </ExternalTextLink>
                ) : null}
                <LicenceLine
                  licence={selected.licence}
                  fetchDate={selected.fetch_date}
                />
              </div>

              {typeof selected.extracted_text === "string" &&
              selected.extracted_text ? (
                <div
                  tabIndex={0}
                  role="document"
                  aria-label="Extracted text"
                  className="max-h-96 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/30 px-4 py-3 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                >
                  {selected.extracted_text}
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  No extracted text is available for this document.
                </p>
              )}

              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setSelectedId(null)}
                >
                  Close
                </Button>
              </DialogFooter>
            </>
          ) : (
            <>
              <DialogHeader>
                <DialogTitle className="sr-only">Document</DialogTitle>
                <DialogDescription className="sr-only">
                  The document could not be loaded.
                </DialogDescription>
              </DialogHeader>
              <p className="py-8 text-sm text-muted-foreground">
                The document could not be loaded.
              </p>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  )
}
