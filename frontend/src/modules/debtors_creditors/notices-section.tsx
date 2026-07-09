/*
  Section 27 creditor notices: the notices table (with the derived claim
  deadline and a live open claims count per notice), a create and edit
  form, and a claims panel in the notice detail dialog where claims can
  be added and their status updated. Claim changes invalidate the
  /creditor-notices cache so the derived safe to distribute state and the
  banner stay current.
*/

import * as React from "react"
import { useQueryClient } from "@tanstack/react-query"

import type { DataTableColumn } from "@/components/shared/data-table"
import { EntityForm } from "@/components/shared/entity-form"
import {
  formatMoney,
  humaniseCode,
} from "@/components/shared/formatters"
import { optionsFromEnum } from "@/components/shared/form-schema"
import { Badge } from "@/components/ui/badge"
import { Skeleton } from "@/components/ui/skeleton"
import { isApiError } from "@/lib/api"
import {
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"

import {
  claimCreateDefaults,
  claimFields,
  claimSchema,
  CLAIM_STATUS_VALUES,
  noticeCreateDefaults,
  noticeEditDefaults,
  noticeFields,
  noticeSchema,
  type ClaimFormValues,
  type NoticeFormValues,
} from "./forms"
import { isOpenClaim, type CreditorNotice, type NoticeClaim } from "./types"
import { emptyToNull, omitEmpty } from "@/modules/assets/payload"
import {
  RegisterSection,
  type DetailFieldDef,
} from "@/modules/assets/register-section"

/** Live count of open claims for one notice, shown in the table. */
function OpenClaimsCount({ noticeId }: { noticeId: string }) {
  const { data, isPending } = useResourceList<NoticeClaim>(
    `/creditor-notices/${noticeId}/claims`,
  )
  if (isPending) {
    return <Skeleton className="h-4 w-8" aria-hidden="true" />
  }
  if (data === null || data === undefined) {
    return <span aria-hidden="true">&ndash;</span>
  }
  return <>{data.filter(isOpenClaim).length}</>
}

const claimStatusOptions = optionsFromEnum(CLAIM_STATUS_VALUES)

/** Claims received against one notice, with add and status update. */
function ClaimsPanel({
  notice,
  writable,
}: {
  notice: CreditorNotice
  writable: boolean
}) {
  const path = `/creditor-notices/${notice.id}/claims`
  const queryClient = useQueryClient()
  const list = useResourceList<NoticeClaim>(path)
  const create = useCreateResource<NoticeClaim, Record<string, unknown>>(path)
  const update = useUpdateResource<NoticeClaim, Record<string, unknown>>(path)
  const [statusError, setStatusError] = React.useState<string | null>(null)
  const panelId = React.useId()

  const claims = (list.data ?? []).filter((claim) => !claim.archived_at)

  /* The derived safe to distribute state depends on claims. */
  async function refreshGuard() {
    await queryClient.invalidateQueries({ queryKey: ["/creditor-notices"] })
  }

  async function handleAdd(values: ClaimFormValues) {
    await create.mutateAsync(omitEmpty(values))
    await refreshGuard()
  }

  async function handleStatusChange(claim: NoticeClaim, status: string) {
    setStatusError(null)
    try {
      await update.mutateAsync({ id: claim.id, data: { status } })
      await refreshGuard()
    } catch (error) {
      setStatusError(
        isApiError(error)
          ? error.message
          : "The claim status could not be updated. Please try again.",
      )
    }
  }

  return (
    <section aria-label="Claims received" className="space-y-3 border-t pt-4">
      <h3 className="text-sm font-semibold">Claims received</h3>
      {list.isPending ? (
        <Skeleton className="h-12 w-full" />
      ) : claims.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No claims recorded against this notice.
        </p>
      ) : (
        <ul className="space-y-2">
          {claims.map((claim) => {
            const selectId = `${panelId}-status-${claim.id}`
            return (
              <li
                key={claim.id}
                className="flex items-center justify-between gap-3 rounded-md border px-3 py-2 text-sm"
              >
                <div>
                  <p className="font-medium">{claim.claimant}</p>
                  <p className="text-muted-foreground">
                    {formatMoney(claim.amount, "Amount not recorded")}
                  </p>
                </div>
                {writable ? (
                  <div>
                    <label htmlFor={selectId} className="sr-only">
                      Status of the claim from {claim.claimant}
                    </label>
                    <select
                      id={selectId}
                      value={claim.status ?? "open"}
                      onChange={(event) =>
                        void handleStatusChange(claim, event.target.value)
                      }
                      className="h-8 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      {claimStatusOptions.map((option) => (
                        <option key={option.value} value={option.value}>
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </div>
                ) : (
                  <Badge variant={isOpenClaim(claim) ? "outline" : "secondary"}>
                    {humaniseCode(claim.status ?? "open")}
                  </Badge>
                )}
              </li>
            )
          })}
        </ul>
      )}
      {statusError ? (
        <p role="alert" className="text-sm text-destructive">
          {statusError}
        </p>
      ) : null}
      {writable ? (
        <div className="space-y-2 border-t pt-4">
          <h4 className="text-sm font-medium">Add a claim</h4>
          <EntityForm<ClaimFormValues>
            key={claims.length}
            schema={claimSchema}
            fields={claimFields}
            defaultValues={claimCreateDefaults}
            onSubmit={handleAdd}
            submitLabel="Add claim"
          />
        </div>
      ) : null}
    </section>
  )
}

export function NoticesSection({ estateId }: { estateId: string | null }) {
  const columns: DataTableColumn<CreditorNotice>[] = [
    {
      key: "gazette_ref",
      header: "Gazette reference",
      value: (row) => row.gazette_ref,
    },
    {
      key: "gazette_date",
      header: "Gazette date",
      value: (row) => row.gazette_date,
      kind: "date",
    },
    {
      key: "local_paper",
      header: "Local paper",
      value: (row) => row.local_paper,
    },
    {
      key: "local_date",
      header: "Local paper date",
      value: (row) => row.local_date,
      kind: "date",
    },
    {
      key: "claim_deadline",
      header: "Claim deadline",
      value: (row) => row.claim_deadline,
      kind: "date",
    },
    {
      key: "open_claims",
      header: "Open claims",
      value: () => null,
      sortable: false,
      render: (row) => <OpenClaimsCount noticeId={row.id} />,
    },
  ]

  const detailFields: DetailFieldDef<CreditorNotice>[] = [
    { label: "Gazette reference", value: (row) => row.gazette_ref },
    {
      label: "Gazette date",
      value: (row) => row.gazette_date,
      kind: "date",
    },
    { label: "Local paper", value: (row) => row.local_paper },
    {
      label: "Local paper date",
      value: (row) => row.local_date,
      kind: "date",
    },
    {
      label: "Claim deadline",
      value: (row) => row.claim_deadline,
      kind: "date",
    },
    {
      label: "Notice safe to distribute",
      value: (row) => row.safe_to_distribute,
      kind: "boolean",
    },
  ]

  return (
    <RegisterSection<CreditorNotice, NoticeFormValues>
      title="Section 27 creditor notices"
      description="Statutory notices placed in The Gazette and a local paper, with the claims received against them."
      path="/creditor-notices"
      itemLabel="notice"
      addLabel="Add notice"
      tableLabel="Creditor notices register"
      filterLabel="Filter notices"
      emptyTitle="No creditor notices recorded yet."
      emptyMessage="Record each Section 27 notice as it is placed; the claim deadline is derived automatically."
      columns={columns}
      estateId={estateId}
      formSchema={noticeSchema}
      formFields={noticeFields}
      createDefaults={noticeCreateDefaults}
      editDefaults={noticeEditDefaults}
      toCreatePayload={(values, estate) =>
        omitEmpty({ ...values, estate_id: estate })
      }
      toUpdatePayload={(values) => emptyToNull({ ...values })}
      detailTitle={(row) =>
        row.gazette_ref ? `Notice ${row.gazette_ref}` : "Creditor notice"
      }
      detailFields={detailFields}
      renderDetailExtra={(row, writable) => (
        <ClaimsPanel notice={row} writable={writable} />
      )}
    />
  )
}
