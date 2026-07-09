/*
  Estate accounts export action: a write-gated button that asks the
  server to render the estate accounts as a PDF
  (POST /exports/estate-accounts). The export returns a document row
  stored in the vault; the success toast offers a Download action to the
  existing GET /documents/{id}/download stream.
*/

import { useMutation, useQueryClient } from "@tanstack/react-query"
import { FileDown } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import { documentDownloadUrl } from "@/modules/documents/upload"

/** The document row the export returns; only the id is load-bearing. */
interface ExportedDocument {
  id: string
  title?: string
}

export function AccountsExportActions() {
  const { role } = useMe()
  const queryClient = useQueryClient()

  const exportAccounts = useMutation({
    mutationFn: () => api.post<ExportedDocument>("/exports/estate-accounts"),
    onSuccess: async (doc) => {
      toast.success("Estate accounts PDF saved to the documents vault.", {
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
          : "The export failed. Please try again.",
      )
    },
  })

  if (!canWrite(role)) return null

  return (
    <Button
      type="button"
      variant="outline"
      onClick={() => exportAccounts.mutate()}
      disabled={exportAccounts.isPending}
    >
      <FileDown aria-hidden="true" />
      {exportAccounts.isPending
        ? "Exporting estate accounts"
        : "Export estate accounts PDF"}
    </Button>
  )
}
