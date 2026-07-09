/*
  IHT export actions: write-gated buttons that ask the server to render
  the IHT form draft and the clearance application draft as PDFs
  (POST /exports/iht-draft, POST /exports/clearance-draft, both with no
  body). Each export returns a document row stored in the vault; the
  success toast offers a Download action to the existing
  GET /documents/{id}/download stream. Exports are drafts for review;
  nothing is filed with HMRC by code.

  Landed contract notes: with no request body, /exports/iht-draft reads
  the latest APPROVED agent forms draft itself and returns 404 when none
  exists (mapped here to a friendlier line); /exports/clearance-draft
  returns 404 until an IHT assessment has been computed.
*/

import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileDown } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import { documentDownloadUrl } from "@/modules/documents/upload"

/** The document row an export returns; only the id is load-bearing. */
interface ExportedDocument {
  id: string
  title?: string
}

function useExportDocument(
  path: string,
  successMessage: string,
  notFoundMessage?: string,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ExportedDocument>(path),
    onSuccess: async (doc) => {
      toast.success(successMessage, {
        action: {
          label: "Download",
          onClick: () =>
            window.open(documentDownloadUrl(doc.id), "_blank", "noopener"),
        },
      })
      await queryClient.invalidateQueries({ queryKey: ["/documents"] })
    },
    onError: (error) => {
      if (isApiError(error) && error.status === 404 && notFoundMessage) {
        toast.error(notFoundMessage)
        return
      }
      toast.error(
        isApiError(error)
          ? error.message
          : "The export failed. Please try again.",
      )
    },
  })
}

export function IhtExportActions() {
  const { role } = useMe()
  const ihtDraft = useExportDocument(
    "/exports/iht-draft",
    "IHT draft PDF saved to the documents vault.",
    "No approved IHT form draft to export yet. Draft the IHT400 pack on the Drafts page and approve it first.",
  )
  const clearanceDraft = useExportDocument(
    "/exports/clearance-draft",
    "Clearance draft PDF saved to the documents vault.",
    "No IHT assessment to draw on yet. Choose Recompute to produce one first.",
  )

  if (!canWrite(role)) return null

  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={() => ihtDraft.mutate()}
        disabled={ihtDraft.isPending}
      >
        <FileDown aria-hidden="true" />
        {ihtDraft.isPending ? "Exporting IHT draft" : "Export IHT draft PDF"}
      </Button>
      <Button
        type="button"
        variant="outline"
        onClick={() => clearanceDraft.mutate()}
        disabled={clearanceDraft.isPending}
      >
        <FileDown aria-hidden="true" />
        {clearanceDraft.isPending
          ? "Exporting clearance draft"
          : "Export clearance draft PDF"}
      </Button>
    </>
  )
}
