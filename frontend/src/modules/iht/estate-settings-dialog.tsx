/*
  Estate settings dialog for the IHT workbench (GET/PUT /estate).

  Serialisation rules, matching backend EstateSettingsUpdate semantics
  (only keys present are applied):
  - claims_rnrb is a tri-state select: "" means Derive automatically and
    serialises as null; "yes"/"no" serialise as true/false. Always sent.
  - The excepted-estate facts (gifts with reservation and the three
    values) treat blank as unknown and serialise as null. Always sent,
    with helper text explaining that unknown is treated cautiously.
  - The percentage shares are never nullable server side, so a cleared
    input is omitted from the payload rather than sent as null.
*/

import { toast } from "sonner"
import { z } from "zod"

import { EntityForm, type EntityField } from "@/components/shared/entity-form"
import { zOptionalDate, zOptionalMoney } from "@/components/shared/form-schema"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

import {
  useUpdateEstateSettings,
  type EstateSettings,
  type EstateSettingsUpdate,
} from "./use-iht"

const SHARE_PATTERN = /^(0(\.\d{1,4})?|1(\.0{1,4})?)$/
const SHARE_MESSAGE = "Enter a share between 0 and 1, for example 0.5"

const zShare = () =>
  z
    .string()
    .trim()
    .refine((value) => value === "" || SHARE_PATTERN.test(value), SHARE_MESSAGE)

const zTriState = () => z.enum(["", "yes", "no"])

const settingsSchema = z.object({
  date_of_death: zOptionalDate(),
  tnrb_pct: zShare(),
  trnrb_pct: zShare(),
  residence_to_descendants_value: zOptionalMoney(),
  charity_share_pct: zShare(),
  claims_rnrb: zTriState(),
  gifts_with_reservation: zTriState(),
  foreign_assets_value: zOptionalMoney(),
  trust_property_value: zOptionalMoney(),
  specified_transfers_value: zOptionalMoney(),
})

type SettingsValues = z.infer<typeof settingsSchema>

const UNKNOWN_HELP =
  "Leave blank if unknown. Unknown is treated cautiously: IHT400 assumed required."

const yesNoOptions = [
  { value: "yes", label: "Yes" },
  { value: "no", label: "No" },
]

const fields: EntityField<SettingsValues>[] = [
  {
    name: "date_of_death",
    label: "Date of death",
    kind: "date",
    required: false,
    description: "Used to derive deadlines and the applicable tax constants.",
  },
  {
    name: "tnrb_pct",
    label: "Transferable nil rate band share",
    kind: "text",
    required: false,
    placeholder: "0",
    description:
      "Share claimed from a predeceased spouse or civil partner, between 0 and 1.",
  },
  {
    name: "trnrb_pct",
    label: "Transferable residence nil rate band share",
    kind: "text",
    required: false,
    placeholder: "0",
    description:
      "Share of the residence band claimed from a predeceased spouse or civil partner, between 0 and 1.",
  },
  {
    name: "residence_to_descendants_value",
    label: "Residence passing to descendants",
    kind: "money",
    required: false,
    description:
      "Value of the home passing to direct descendants, for the residence nil rate band.",
  },
  {
    name: "charity_share_pct",
    label: "Charity share",
    kind: "text",
    required: false,
    placeholder: "0",
    description:
      "Share of the estate left to charity, between 0 and 1. At least 0.1 attracts the reduced 36% rate.",
  },
  {
    name: "claims_rnrb",
    label: "Residence nil rate band claim",
    kind: "select",
    required: false,
    placeholder: "Derive automatically",
    options: yesNoOptions,
    description:
      "Derive automatically claims the band when a qualifying residence passes to descendants.",
  },
  {
    name: "gifts_with_reservation",
    label: "Gifts with reservation of benefit",
    kind: "select",
    required: false,
    placeholder: "Unknown",
    options: yesNoOptions,
    description:
      "Leave as Unknown if not yet established. Unknown is treated cautiously: IHT400 assumed required.",
  },
  {
    name: "foreign_assets_value",
    label: "Foreign assets value",
    kind: "money",
    required: false,
    description: UNKNOWN_HELP,
  },
  {
    name: "trust_property_value",
    label: "Trust property value",
    kind: "money",
    required: false,
    description: UNKNOWN_HELP,
  },
  {
    name: "specified_transfers_value",
    label: "Specified transfers value",
    kind: "money",
    required: false,
    description: UNKNOWN_HELP,
  },
]

function toTriState(value: boolean | null): "" | "yes" | "no" {
  if (value === true) return "yes"
  if (value === false) return "no"
  return ""
}

function toDefaults(settings: EstateSettings): SettingsValues {
  return {
    date_of_death: settings.date_of_death ?? "",
    tnrb_pct: settings.tnrb_pct ?? "",
    trnrb_pct: settings.trnrb_pct ?? "",
    residence_to_descendants_value:
      settings.residence_to_descendants_value ?? "",
    charity_share_pct: settings.charity_share_pct ?? "",
    claims_rnrb: toTriState(settings.claims_rnrb),
    gifts_with_reservation: toTriState(settings.gifts_with_reservation),
    foreign_assets_value: settings.foreign_assets_value ?? "",
    trust_property_value: settings.trust_property_value ?? "",
    specified_transfers_value: settings.specified_transfers_value ?? "",
  }
}

function fromTriState(value: "" | "yes" | "no"): boolean | null {
  if (value === "yes") return true
  if (value === "no") return false
  return null
}

function toPayload(values: SettingsValues): EstateSettingsUpdate {
  const nullable = (value: string) =>
    value.trim() === "" ? null : value.trim()

  const payload: EstateSettingsUpdate = {
    date_of_death: values.date_of_death || null,
    residence_to_descendants_value: nullable(
      values.residence_to_descendants_value,
    ),
    claims_rnrb: fromTriState(values.claims_rnrb),
    gifts_with_reservation: fromTriState(values.gifts_with_reservation),
    foreign_assets_value: nullable(values.foreign_assets_value),
    trust_property_value: nullable(values.trust_property_value),
    specified_transfers_value: nullable(values.specified_transfers_value),
  }
  if (values.tnrb_pct.trim() !== "") payload.tnrb_pct = values.tnrb_pct.trim()
  if (values.trnrb_pct.trim() !== "")
    payload.trnrb_pct = values.trnrb_pct.trim()
  if (values.charity_share_pct.trim() !== "")
    payload.charity_share_pct = values.charity_share_pct.trim()
  return payload
}

export interface EstateSettingsDialogProps {
  settings: EstateSettings
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function EstateSettingsDialog({
  settings,
  open,
  onOpenChange,
}: EstateSettingsDialogProps) {
  const update = useUpdateEstateSettings()

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Estate settings</DialogTitle>
          <DialogDescription>
            The facts the deterministic engine assesses from. Saving
            triggers a fresh assessment. For the excepted-estate facts,
            unknown is treated cautiously: IHT400 assumed required.
          </DialogDescription>
        </DialogHeader>
        <EntityForm
          schema={settingsSchema}
          fields={fields}
          defaultValues={toDefaults(settings)}
          submitLabel="Save settings"
          onCancel={() => onOpenChange(false)}
          onSubmit={async (values) => {
            await update.mutateAsync(toPayload(values))
            toast.success("Estate settings saved")
            onOpenChange(false)
          }}
        />
      </DialogContent>
    </Dialog>
  )
}
