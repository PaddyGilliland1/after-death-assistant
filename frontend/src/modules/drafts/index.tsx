/*
  Drafts module: the human-approval surface for agent output (guardrail
  1 made visible). Pending drafts from GET /agents/drafts are listed by
  their approval reference; the draft content is loaded from the draft
  document (GET /documents/{draft_id}/download returns the stored
  {draft_kind, payload} JSON); approving posts to
  POST /agents/drafts/{approval_id}/approve behind a confirmation that
  states exactly what approval means: it records the decision, and
  nothing is ever sent or filed by this application. The agents API is
  write-role only, so viewers get a calm explanation instead of a list.
*/

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { ConfirmDialog } from "@/components/shared/confirm-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { PageHeader } from "@/components/shared/page-header"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import { useResourceList } from "@/lib/hooks/use-resource"
import { documentDownloadUrl } from "@/modules/documents/upload"

import { DraftDetailDialog } from "./draft-detail"
import {
  APPROVAL_MEANING,
  draftKind,
  draftSummary,
  kindLabel,
  suggestionsOf,
  type PendingDraft,
} from "./draft-meta"
import { NewDraftActions } from "./new-draft-actions"

const DRAFTS_PATH = "/agents/drafts"

const columns: DataTableColumn<PendingDraft>[] = [
  {
    key: "kind",
    header: "Kind",
    value: (row) => kindLabel(draftKind(row)),
    kind: "badge",
  },
  {
    key: "summary",
    header: "Draft",
    value: (row) => draftSummary(row),
  },
  {
    key: "created",
    header: "Created",
    value: (row) => row.created_at ?? null,
    kind: "date",
  },
  {
    key: "created_by",
    header: "Created by",
    value: (row) => row.created_by ?? null,
  },
]

interface ConfirmState {
  draft: PendingDraft
  /** Ticked suggestion indices; null approves everything in the draft. */
  accepted: number[] | null
}

export default function DraftsPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()

  /* The agents API is write-role only; do not fetch as a viewer. */
  const draftsQuery = useResourceList<PendingDraft>(DRAFTS_PATH, {
    enabled: writer,
  })
  const [selectedId, setSelectedId] = React.useState<string | null>(null)
  const [confirming, setConfirming] = React.useState<ConfirmState | null>(null)

  const drafts = React.useMemo(
    () => draftsQuery.data ?? [],
    [draftsQuery.data],
  )
  const selected =
    drafts.find((draft) => draft.approval_id === selectedId) ?? null

  /* The draft content lives in the draft document's stored JSON. */
  const payloadQuery = useQuery({
    queryKey: [DRAFTS_PATH, "payload", selected?.draft_id ?? ""],
    queryFn: () =>
      api.get<unknown>(`/documents/${selected?.draft_id}/download`),
    enabled: Boolean(selected?.draft_id),
    retry: false,
  })

  /*
    An approved letter can be rendered to PDF (POST /exports/letter/
    {draft_id}); the export is a local document row, never a send.
  */
  const exportLetter = useMutation({
    mutationFn: (draftId: string) =>
      api.post<{ id: string }>(`/exports/letter/${draftId}`),
    onSuccess: async (doc) => {
      toast.success("Letter PDF saved to the documents vault.", {
        action: {
          label: "Download",
          onClick: () =>
            window.open(documentDownloadUrl(doc.id), "_blank", "noopener"),
        },
      })
      await queryClient.invalidateQueries({ queryKey: ["/documents"] })
    },
    onError: (error) => {
      toast.error(
        isApiError(error)
          ? error.message
          : "The letter could not be exported. Please try again.",
      )
    },
  })

  const approve = useMutation({
    mutationFn: ({ draft, accepted }: ConfirmState) =>
      api.post<unknown>(
        `${DRAFTS_PATH}/${draft.approval_id}/approve`,
        accepted === null ? {} : { accepted },
      ),
    onSuccess: async (_result, { draft }) => {
      const letterDraftId =
        draftKind(draft) === "letter" && draft.draft_id ? draft.draft_id : null
      toast.success(
        "Draft approved. Your decision is recorded; submitting or sending remains yours to do.",
        letterDraftId
          ? {
              action: {
                label: "Export letter PDF",
                onClick: () => exportLetter.mutate(letterDraftId),
              },
            }
          : undefined,
      )
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: [DRAFTS_PATH] }),
        queryClient.invalidateQueries({ queryKey: ["/tasks"] }),
        queryClient.invalidateQueries({ queryKey: ["/documents"] }),
        queryClient.invalidateQueries({ queryKey: ["/approvals"] }),
      ])
    },
  })

  function confirmDescription(state: ConfirmState): string {
    if (draftKind(state.draft) === "tasks") {
      const total = suggestionsOf(payloadQuery.data).length
      const count = state.accepted === null ? total : state.accepted.length
      const lead =
        count === 0
          ? "No suggestions are ticked, so no tasks will be created."
          : `${count} of ${total} suggestion${total === 1 ? "" : "s"} will be created as tasks.`
      return `${lead} ${APPROVAL_MEANING}`
    }
    return APPROVAL_MEANING
  }

  return (
    <section aria-label="Drafts">
      <PageHeader
        title="Drafts"
        description="Everything the assistant has drafted, waiting for a person to review and approve."
      />

      <p
        role="note"
        className="mb-6 rounded-md border bg-muted/50 px-4 py-3 text-sm text-muted-foreground"
      >
        The assistant only drafts. Nothing is sent or filed by this
        application: a draft stays a draft until a person approves it, and
        you remain responsible for submitting documents to HMRC or sending
        letters yourself.
      </p>

      {!writer ? (
        <p className="text-sm text-muted-foreground" role="status">
          Agent drafts are visible to executors and admins only. Approved
          letters and forms appear in the documents vault.
        </p>
      ) : (
        <>
          <NewDraftActions />

          {!draftsQuery.isPending &&
          (draftsQuery.isError || draftsQuery.data === null) ? (
            <p className="text-sm text-muted-foreground" role="status">
              The drafting assistant is not connected yet. Drafts will
              appear here once the server is ready.
            </p>
          ) : (
            <DataTable
              columns={columns}
              rows={draftsQuery.data}
              rowKey={(row) => row.approval_id}
              isLoading={draftsQuery.isPending}
              label="Pending drafts"
              filterLabel="Filter drafts"
              emptyTitle="No drafts are waiting for review."
              emptyMessage="Use the actions above to ask the assistant for a form draft, a letter draft or task suggestions."
              onRowClick={(row) => setSelectedId(row.approval_id)}
            />
          )}
        </>
      )}

      <DraftDetailDialog
        draft={selected}
        payload={payloadQuery.data}
        payloadPending={Boolean(selected?.draft_id) && payloadQuery.isPending}
        payloadError={payloadQuery.isError}
        open={selected !== null && confirming === null}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null)
        }}
        writer={writer}
        onApprove={(draft, accepted) => setConfirming({ draft, accepted })}
      />

      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => {
          if (!open) setConfirming(null)
        }}
        title="Approve this draft?"
        description={confirming ? confirmDescription(confirming) : ""}
        confirmLabel="Approve"
        onConfirm={async () => {
          if (!confirming) return
          await approve.mutateAsync(confirming)
          setConfirming(null)
          setSelectedId(null)
        }}
      />
    </section>
  )
}
