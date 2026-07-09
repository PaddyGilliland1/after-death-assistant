/*
  TypeScript interfaces for the API resources the frontend consumes.

  Field names mirror backend/app/models/*.py exactly. Conventions:
  - UUIDs and timestamps arrive as strings.
  - Dates are ISO strings (YYYY-MM-DD).
  - Money (backend Decimal) arrives as a string in JSON; format at display
    with the helpers in src/components/shared/formatters.ts.
*/

/** A money value serialised from a backend Decimal. Format at display. */
export type Money = string

/** ISO date string, YYYY-MM-DD. */
export type IsoDate = string

/** ISO datetime string with timezone. */
export type IsoDateTime = string

/** UUID as a string. */
export type Uuid = string

/* ---------------------------------------------------------------- enums */

export type Role = "executor" | "admin" | "viewer"

export type ContactCategory =
  | "bank"
  | "nsandi"
  | "insurer"
  | "pension"
  | "utility"
  | "telecom"
  | "tv_licensing"
  | "streaming"
  | "council"
  | "hmrc"
  | "probate_registry"
  | "solicitor"
  | "accountant"
  | "valuer"
  | "registrar"
  | "gp"
  | "dentist"
  | "optician"
  | "employer"
  | "landlord"
  | "care_agency"
  | "beneficiary"
  | "gift_recipient"
  | "creditor"
  | "debtor"
  | "executor"
  | "membership"
  | "other"

export type OwnershipType = "sole" | "joint_tenants" | "tenants_in_common"

export type ValueBasis = "estimate" | "confirmed"

export type IhtTreatment = "funeral_deductible" | "admin_not_deductible"

export type LegacyType = "pecuniary" | "specific" | "residuary"

/* ----------------------------------------------------------- base rows */

/** Identity and provenance columns shared by every table. */
export interface BaseRow {
  id: Uuid
  created_at: IsoDateTime
  updated_at: IsoDateTime
  created_by: string
}

/** Soft delete columns. Rows are archived, never physically deleted. */
export interface Archivable {
  archived_at: IsoDateTime | null
  archive_reason: string | null
}

/** Base for all business rows: identity, soft delete and estate scope. */
export interface EstateScopedRow extends BaseRow, Archivable {
  estate_id: Uuid
}

/* ------------------------------------------------------------- estate */

export interface Estate extends BaseRow, Archivable {
  name: string
  date_of_death: IsoDate | null
  grant_date: IsoDate | null
  constants_version: string | null
  nrb: Money | null
  rnrb: Money | null
  taper_threshold: Money | null
  tnrb_pct: string
  trnrb_pct: string
  residence_to_descendants_value: Money | null
  charity_share_pct: string
  claims_rnrb: boolean | null
  gifts_with_reservation: boolean | null
  foreign_assets_value: Money | null
  trust_property_value: Money | null
  specified_transfers_value: Money | null
}

/*
  Shape of GET /estate/summary. Every field is optional so the dashboard
  degrades gracefully while the backend catches up. Money aggregates may
  arrive as strings (Decimal) or numbers depending on how the endpoint
  computes them; display code should tolerate both.
*/
export interface EstateSummary {
  gross_assets_at_dod?: Money | number | null
  net_estate?: Money | number | null
  iht_due?: Money | number | null
  open_task_count?: number | null
  unnotified_contact_count?: number | null
  costs_total?: Money | number | null
}

/* -------------------------------------------------------------- assets */

export interface Asset extends EstateScopedRow {
  category: string
  sub_type: string | null
  description: string
  holder_contact_id: Uuid | null
  account_reference: string | null
  ownership: OwnershipType
  tic_share_pct: string | null
  dod_value: Money | null
  value_basis: ValueBasis
  valuation_source: string | null
  valuation_date: IsoDate | null
  current_or_realised_value: Money | null
  realised_date: IsoDate | null
  income_since_death: Money | null
  iht_schedule: string | null
  rnrb_qualifying: boolean
  passes_outside_estate: boolean
  status: string | null
}

export interface Liability extends EstateScopedRow {
  type: string
  creditor_contact_id: Uuid | null
  amount: Money
  as_at_date: IsoDate | null
  status: string | null
  iht_deductible: boolean
}

/* -------------------------------------------------- debtors and creditors */

export interface Debtor extends EstateScopedRow {
  source_contact_id: Uuid | null
  type: string
  amount_expected: Money | null
  amount_received: Money | null
  status: string | null
  expected_date: IsoDate | null
  received_into_asset_id: Uuid | null
}

export interface Creditor extends EstateScopedRow {
  creditor_contact_id: Uuid | null
  type: string
  amount_claimed: Money | null
  amount_agreed: Money | null
  amount_paid: Money | null
  status: string | null
  priority_class: string | null
  paid_from_asset_id: Uuid | null
}

/* ------------------------------------------------------------- contacts */

export interface Contact extends EstateScopedRow {
  kind: string | null
  category: ContactCategory
  name: string
  org: string | null
  relationship: string | null
  email: string | null
  phone: string | null
  address: string | null
  references: string[]
  holds_or_handles: string | null
  notify_required: boolean
  notification_status: string | null
  notified_date: IsoDate | null
  notified_method: string | null
}

/* ---------------------------------------------------------------- tasks */

export interface TaskChecklistItem {
  text: string
  done: boolean
}

export interface Task extends EstateScopedRow {
  title: string
  description: string | null
  assignees: string[]
  status: string | null
  priority: string | null
  start_date: IsoDate | null
  due_date: IsoDate | null
  blocked_by: string[]
  blocks: string[]
  checklist: TaskChecklistItem[]
  process_step_id: Uuid | null
  source: string | null
  reminder: IsoDate | null
  executor_private: boolean
}

/* ---------------------------------------------------------------- costs */

export interface Cost extends EstateScopedRow {
  description: string
  category: string
  amount: Money
  vat: Money | null
  date: IsoDate
  paid_by: string | null
  payment_method: string | null
  reimbursable: boolean
  reimbursed: boolean
  reimbursed_date: IsoDate | null
  iht_treatment: IhtTreatment
  receipt_document_id: Uuid | null
  executor_private: boolean
}

/* --------------------------------------------------------- beneficiaries */

export interface BeneficiaryLegacy extends EstateScopedRow {
  beneficiary_contact_id: Uuid
  legacy_type: LegacyType
  amount_or_share: string | null
  exempt_or_chargeable: string | null
  tax_bearing: boolean | null
  status: string | null
}

/* -------------------------------------------------------------- decisions */

export interface DecisionOption {
  option: string
  notes?: string
}

/** Immutable executor decision. No soft delete columns by design. */
export interface Decision extends BaseRow {
  estate_id: Uuid
  date: IsoDate
  title: string
  rationale: string | null
  options_considered: DecisionOption[] | null
  agreed_by: string[]
  made_by: string
  executor_private: boolean
}

/* -------------------------------------------------------------- documents */

export interface DocumentLink {
  entity_type: string
  entity_id: string
}

export interface Document extends EstateScopedRow {
  title: string
  type: string | null
  file_key: string | null
  mime: string | null
  version: number
  access_roles: string[]
  links: DocumentLink[]
  executor_private: boolean
}

/* ---------------------------------------------------------- notifications */

export interface Notification extends EstateScopedRow {
  user_id: string
  event_type: string
  entity_ref: string | null
  message: string
  read_at: IsoDateTime | null
}

/* ---------------------------------------------------- process and deadlines */

export interface DeadlineReminder {
  kind?: string
  basis?: string
  date?: IsoDate
  sent?: boolean
  [key: string]: unknown
}

export interface Deadline extends EstateScopedRow {
  type: string
  derived_date: IsoDate | null
  reminders: DeadlineReminder[]
}

export interface ProcessStep extends EstateScopedRow {
  order: number
  name: string
  status: string | null
  deadline_id: Uuid | null
}

/* ------------------------------------------------------------------- iht */

export interface IhtAssessment extends EstateScopedRow {
  snapshot: Record<string, unknown>
  constants_version: string
}
