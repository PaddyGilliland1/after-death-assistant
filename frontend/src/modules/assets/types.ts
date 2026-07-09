/*
  Types local to the assets module. Field names mirror
  backend/app/schemas/registers.py (ValuationEventRead).
*/

import type { EstateScopedRow, IsoDate, Money, Uuid, ValueBasis } from "@/lib/types"

/** A dated valuation of an asset (GET /assets/{id}/valuations). */
export interface ValuationEvent extends EstateScopedRow {
  asset_id: Uuid
  value: Money
  basis: ValueBasis
  source: string | null
  date: IsoDate
}
