/*
  Types local to the debtors and creditors module. Field names mirror
  backend/app/schemas/registers.py (CreditorNoticeRead, NoticeClaimRead,
  SafeToDistributeResponse).
*/

import type { EstateScopedRow, IsoDate, Money, Uuid } from "@/lib/types"

/** A Trustee Act 1925 Section 27 notice (GET /creditor-notices). */
export interface CreditorNotice extends EstateScopedRow {
  gazette_ref: string | null
  gazette_date: IsoDate | null
  local_paper: string | null
  local_date: IsoDate | null
  claim_deadline: IsoDate | null
  safe_to_distribute: boolean | null
}

/** A claim received against a notice (GET /creditor-notices/{id}/claims). */
export interface NoticeClaim extends EstateScopedRow {
  creditor_notice_id: Uuid
  claimant: string
  amount: Money | null
  status: string | null
}

/** GET /creditor-notices/safe-to-distribute. */
export interface SafeToDistribute {
  safe_to_distribute: boolean
  checked_on: IsoDate
  reasons: string[]
}

/*
  Claim states that no longer block distribution. Mirrors
  CLOSED_CLAIM_STATUSES in backend/app/api/creditor_notices.py; anything
  else, including no status at all, counts as open.
*/
export const CLOSED_CLAIM_STATUSES = new Set([
  "resolved",
  "rejected",
  "withdrawn",
  "paid",
  "settled",
  "closed",
])

/** True when a claim still blocks distribution. */
export function isOpenClaim(claim: NoticeClaim): boolean {
  if (claim.archived_at) return false
  if (!claim.status) return true
  return !CLOSED_CLAIM_STATUSES.has(claim.status.toLowerCase())
}
