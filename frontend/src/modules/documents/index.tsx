/*
  Documents module: the estate's document vault. Lists documents from
  GET /documents in a DataTable, uploads new files with multipart POSTs
  (see upload.ts; the shared api client is JSON only), streams downloads
  from GET /documents/{id}/download, attaches new versions and archives
  with a reason. Viewers get a read-only list; the server enforces
  access_roles and executor_private, the UI only mirrors them.
*/

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Download, FileUp } from "lucide-react"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { formatDate, humaniseCode } from "@/components/shared/formatters"
import { PageHeader } from "@/components/shared/page-header"
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
import { Input } from "@/components/ui/input"
import { api, isApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import { useResourceList } from "@/lib/hooks/use-resource"

import {
  documentDownloadUrl,
  uploadDocument,
  uploadDocumentVersion,
} from "./upload"

const DOCUMENTS_PATH = "/documents"

/* Shape returned by the P1 backend (DocumentOut in app/schemas/collab.py). */
interface DocumentRow {
  id: string
  title: string
  type: string | null
  mime: string | null
  version: number
  access_roles: string[]
  executor_private: boolean
  links: Array<Record<string, unknown>>
  created_at: string
  created_by: string
}

const DOCUMENT_TYPES = [
  { value: "will", label: "Will" },
  { value: "death_certificate", label: "Death certificate" },
  { value: "grant_of_probate", label: "Grant of probate" },
  { value: "bank_statement", label: "Bank statement" },
  { value: "valuation", label: "Valuation" },
  { value: "letter", label: "Letter" },
  { value: "receipt", label: "Receipt" },
  { value: "form", label: "Form" },
  { value: "other", label: "Other" },
] as const

const ACCESS_ROLE_OPTIONS = [
  { value: "executor", label: "Executor" },
  { value: "admin", label: "Admin" },
  { value: "viewer", label: "Viewer" },
] as const

function accessRolesLabel(roles: string[]): string {
  if (roles.length === 0) return "All roles"
  return roles.map(humaniseCode).join(", ")
}

const selectClassName =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:cursor-not-allowed disabled:opacity-50"

interface UploadDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

function UploadDialog({ open, onOpenChange }: UploadDialogProps) {
  const queryClient = useQueryClient()
  const [title, setTitle] = React.useState("")
  const [type, setType] = React.useState("")
  const [file, setFile] = React.useState<File | null>(null)
  const [accessRoles, setAccessRoles] = React.useState<string[]>([])
  const [executorPrivate, setExecutorPrivate] = React.useState(false)
  const [validationError, setValidationError] = React.useState<string | null>(
    null,
  )
  const [serverError, setServerError] = React.useState<string | null>(null)
  const [isPending, setIsPending] = React.useState(false)

  const titleId = React.useId()
  const typeId = React.useId()
  const fileId = React.useId()
  const privateId = React.useId()

  function reset() {
    setTitle("")
    setType("")
    setFile(null)
    setAccessRoles([])
    setExecutorPrivate(false)
    setValidationError(null)
    setServerError(null)
  }

  function handleOpenChange(next: boolean) {
    if (isPending) return
    if (!next) reset()
    onOpenChange(next)
  }

  function toggleRole(role: string) {
    setAccessRoles((current) =>
      current.includes(role)
        ? current.filter((item) => item !== role)
        : [...current, role],
    )
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setServerError(null)

    if (!title.trim()) {
      setValidationError("Please give the document a title.")
      return
    }
    if (!file) {
      setValidationError("Please choose a file to upload.")
      return
    }
    setValidationError(null)

    setIsPending(true)
    try {
      await uploadDocument({
        file,
        title: title.trim(),
        type: type || undefined,
        accessRoles,
        executorPrivate,
      })
      await queryClient.invalidateQueries({ queryKey: [DOCUMENTS_PATH] })
      reset()
      onOpenChange(false)
    } catch (cause) {
      setServerError(
        isApiError(cause)
          ? cause.message
          : "The upload failed. Please try again.",
      )
    } finally {
      setIsPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <form onSubmit={handleSubmit} noValidate>
          <DialogHeader>
            <DialogTitle>Upload a document</DialogTitle>
            <DialogDescription>
              The file is stored in the vault and linked to this estate.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-1.5">
              <label htmlFor={titleId} className="text-sm font-medium">
                Title
              </label>
              <Input
                id={titleId}
                value={title}
                disabled={isPending}
                onChange={(event) => setTitle(event.target.value)}
                placeholder="For example: Grant of probate"
              />
            </div>

            <div className="space-y-1.5">
              <label htmlFor={typeId} className="text-sm font-medium">
                Type
              </label>
              <select
                id={typeId}
                value={type}
                disabled={isPending}
                onChange={(event) => setType(event.target.value)}
                className={selectClassName}
              >
                <option value="">Not specified</option>
                {DOCUMENT_TYPES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1.5">
              <label htmlFor={fileId} className="text-sm font-medium">
                File
              </label>
              <Input
                id={fileId}
                type="file"
                disabled={isPending}
                onChange={(event) =>
                  setFile(event.target.files?.[0] ?? null)
                }
              />
            </div>

            <fieldset className="space-y-1.5">
              <legend className="text-sm font-medium">
                Who can see this document
              </legend>
              <p className="text-xs text-muted-foreground">
                Leave every box unticked to allow all roles.
              </p>
              <div className="flex flex-wrap gap-4">
                {ACCESS_ROLE_OPTIONS.map((option) => (
                  <label
                    key={option.value}
                    className="flex items-center gap-2 text-sm"
                  >
                    <input
                      type="checkbox"
                      checked={accessRoles.includes(option.value)}
                      disabled={isPending}
                      onChange={() => toggleRole(option.value)}
                      className="size-4"
                    />
                    {option.label}
                  </label>
                ))}
              </div>
            </fieldset>

            <label
              htmlFor={privateId}
              className="flex items-center gap-2 text-sm"
            >
              <input
                id={privateId}
                type="checkbox"
                checked={executorPrivate}
                disabled={isPending}
                onChange={(event) => setExecutorPrivate(event.target.checked)}
                className="size-4"
              />
              Executor private (never shown to viewers)
            </label>

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
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending ? "Uploading" : "Upload"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

interface DetailDialogProps {
  document: DocumentRow | null
  onOpenChange: (open: boolean) => void
  writer: boolean
  onArchive: (document: DocumentRow) => void
}

function DetailDialog({
  document,
  onOpenChange,
  writer,
  onArchive,
}: DetailDialogProps) {
  const queryClient = useQueryClient()
  const [versionFile, setVersionFile] = React.useState<File | null>(null)
  const [versionError, setVersionError] = React.useState<string | null>(null)
  const [isUploading, setIsUploading] = React.useState(false)
  const versionFileId = React.useId()

  React.useEffect(() => {
    setVersionFile(null)
    setVersionError(null)
  }, [document?.id])

  async function handleNewVersion() {
    if (!document || !versionFile) return
    setVersionError(null)
    setIsUploading(true)
    try {
      await uploadDocumentVersion(document.id, versionFile)
      await queryClient.invalidateQueries({ queryKey: [DOCUMENTS_PATH] })
      onOpenChange(false)
    } catch (cause) {
      setVersionError(
        isApiError(cause)
          ? cause.message
          : "The new version could not be uploaded. Please try again.",
      )
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <Dialog open={document !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        {document ? (
          <>
            <DialogHeader>
              <DialogTitle>{document.title}</DialogTitle>
              <DialogDescription>
                Version {document.version}
                {document.type ? ` · ${humaniseCode(document.type)}` : ""}
                {document.created_at
                  ? ` · uploaded ${formatDate(document.created_at)}`
                  : ""}
              </DialogDescription>
            </DialogHeader>

            <dl className="space-y-2 text-sm">
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Access</dt>
                <dd>{accessRolesLabel(document.access_roles)}</dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Visibility</dt>
                <dd>
                  {document.executor_private ? (
                    <Badge variant="outline">Executor private</Badge>
                  ) : (
                    "Shared"
                  )}
                </dd>
              </div>
              <div className="flex justify-between gap-4">
                <dt className="text-muted-foreground">Uploaded by</dt>
                <dd>{document.created_by || "Unknown"}</dd>
              </div>
            </dl>

            <div className="flex flex-wrap items-center gap-2">
              <Button asChild variant="outline" size="sm">
                <a
                  href={documentDownloadUrl(document.id)}
                  download
                  rel="noopener"
                >
                  <Download aria-hidden="true" />
                  Download
                </a>
              </Button>
            </div>

            {writer ? (
              <div className="space-y-3 border-t pt-4">
                <div className="space-y-1.5">
                  <label
                    htmlFor={versionFileId}
                    className="text-sm font-medium"
                  >
                    Upload a new version
                  </label>
                  <div className="flex items-center gap-2">
                    <Input
                      id={versionFileId}
                      type="file"
                      disabled={isUploading}
                      onChange={(event) =>
                        setVersionFile(event.target.files?.[0] ?? null)
                      }
                    />
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      disabled={!versionFile || isUploading}
                      onClick={handleNewVersion}
                    >
                      <FileUp aria-hidden="true" />
                      {isUploading ? "Uploading" : "Upload version"}
                    </Button>
                  </div>
                  {versionError ? (
                    <p role="alert" className="text-sm text-destructive">
                      {versionError}
                    </p>
                  ) : null}
                </div>

                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  onClick={() => onArchive(document)}
                >
                  Archive document
                </Button>
              </div>
            ) : null}
          </>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}

export default function DocumentsPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()

  const documentsQuery = useResourceList<DocumentRow>(DOCUMENTS_PATH)
  const [uploadOpen, setUploadOpen] = React.useState(false)
  const [selected, setSelected] = React.useState<DocumentRow | null>(null)
  const [archiving, setArchiving] = React.useState<DocumentRow | null>(null)

  /*
    Archive with the reason in the JSON body so sensitive text never
    lands in URLs or proxy logs.
  */
  const archive = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.delete(`${DOCUMENTS_PATH}/${id}`, { reason }),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: [DOCUMENTS_PATH] }),
  })

  const columns: DataTableColumn<DocumentRow>[] = [
    {
      key: "title",
      header: "Title",
      value: (row) => row.title,
    },
    {
      key: "type",
      header: "Type",
      value: (row) => (row.type ? humaniseCode(row.type) : null),
      kind: "badge",
    },
    {
      key: "version",
      header: "Version",
      value: (row) => row.version,
      align: "right",
    },
    {
      key: "uploaded",
      header: "Uploaded",
      value: (row) => row.created_at,
      kind: "date",
    },
    {
      key: "access",
      header: "Access",
      value: (row) => accessRolesLabel(row.access_roles),
    },
    {
      key: "private",
      header: "Private",
      value: (row) => (row.executor_private ? "Private" : null),
      render: (row) =>
        row.executor_private ? (
          <Badge variant="outline">Private</Badge>
        ) : (
          <span aria-hidden="true">&ndash;</span>
        ),
    },
  ]

  return (
    <section aria-label="Documents">
      <PageHeader
        title="Documents"
        description="Store papers, letters and evidence, linked to the records they support."
        actionLabel="Upload document"
        onAction={() => setUploadOpen(true)}
      />

      {!documentsQuery.isPending &&
      (documentsQuery.isError || documentsQuery.data === null) ? (
        <p className="text-sm text-muted-foreground" role="status">
          The document vault is not available yet. It will appear here once
          the server is connected.
        </p>
      ) : (
        <DataTable
          columns={columns}
          rows={documentsQuery.data}
          rowKey={(row) => row.id}
          isLoading={documentsQuery.isPending}
          label="Documents"
          filterLabel="Filter documents"
          emptyTitle="The document vault is empty."
          emptyMessage="It keeps the estate's paperwork safe: the will, the death certificate, the grant, statements, valuations and letters, each linked to the records it supports."
          onRowClick={(row) => setSelected(row)}
        />
      )}

      <UploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />

      <DetailDialog
        document={selected}
        onOpenChange={(open) => {
          if (!open) setSelected(null)
        }}
        writer={writer}
        onArchive={(document) => {
          setSelected(null)
          setArchiving(document)
        }}
      />

      <ArchiveDialog
        open={archiving !== null}
        onOpenChange={(open) => {
          if (!open) setArchiving(null)
        }}
        itemLabel="document"
        onConfirm={async (reason) => {
          if (!archiving) return
          await archive.mutateAsync({ id: archiving.id, reason })
        }}
      />
    </section>
  )
}
