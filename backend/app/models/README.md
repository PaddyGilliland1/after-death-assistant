# app/models

SQLModel tables implementing build contract section 6 (`claude-code-build-prompt.md`).

Conventions: UUID primary keys, `created_at`/`updated_at` (UTC, timezone-aware),
`created_by` (email), soft delete (`archived_at`, `archive_reason`) and `estate_id`
scoping on all business tables. Money is `Numeric(14, 2)` mapped to `Decimal`.
Enums are str-based Python enums stored as strings (`native_enum=False`).

| Module | Contract section 6 entities |
|--------|-----------------------------|
| `base.py` | Shared bases: `TableBase`, `SoftDeleteMixin`, `EstateScopedBase`; `utcnow`, `TZDateTime`, `MoneyType`, `PctType` |
| `enums.py` | `ContactCategory`, `OwnershipType`, `ValueBasis`, `IhtTreatment`, `LegacyType`, `ReliefType`; `str_enum_type` helper |
| `estate.py` | `estate` |
| `contacts.py` | `contact`, `contact_interaction` |
| `assets.py` | `asset`, `valuation_event` |
| `liabilities.py` | `liability` |
| `debtors_creditors.py` | `debtor`, `creditor`, `creditor_notice`, `notice_claim` |
| `costs.py` | `cost` |
| `decisions.py` | `decision` (Module 19 executor decision log; immutable by convention, no soft delete, API layer forbids update/delete) |
| `beneficiaries.py` | `beneficiary_legacy`, `distribution` |
| `tasks.py` | `task`, `task_comment` |
| `process.py` | `process_step`, `deadline` |
| `documents.py` | `document` |
| `iht.py` | `iht_assessment` |
| `reliefs.py` | `relief` |
| `admin_tax.py` | `admin_tax` |
| `digital.py` | `digital_item` |
| `knowledge.py` | `knowledge_doc`, `knowledge_chunk` (pgvector embedding, dimension 1024) |
| `notifications.py` | `notification` |
| `audit.py` | `audit_event`, `approval` |
| `links.py` | `link` (generic cross-reference table) |

29 tables in total. Importing `app.models` registers them all on
`SQLModel.metadata` for Alembic autogenerate.

Additional conventions from the spec validation follow-up:

- `estate.claims_rnrb` is nullable; `None` means derive at the app layer as
  `residence_to_descendants_value > 0`. The excepted-estate disqualifier
  fields (`gifts_with_reservation`, `foreign_assets_value`,
  `trust_property_value`, `specified_transfers_value`) are all nullable;
  `None` means unknown and must be treated conservatively.
- `executor_private: bool` on `document`, `contact_interaction`, `task`,
  `cost` and `decision`: rows flagged true are never returned to the viewer
  role; enforced server-side.
