/*
  Assets and liabilities module (P1 registers). Two sections on one page:
  the assets register (with valuation history per asset) and the
  liabilities register. Contact names come from /contacts so holders and
  creditors show as names rather than ids.
*/

import { PageHeader } from "@/components/shared/page-header"
import type { SelectOption } from "@/components/shared/form-schema"
import { useResourceList } from "@/lib/hooks/use-resource"
import type { Contact } from "@/lib/types"

import { AssetsSection } from "./assets-section"
import { LiabilitiesSection } from "./liabilities-section"
import { useEstateId } from "./use-estate-id"

export default function AssetsPage() {
  const { estateId } = useEstateId()
  const contactsQuery = useResourceList<Contact>("/contacts")

  const contacts = (contactsQuery.data ?? []).filter(
    (contact) => !contact.archived_at,
  )
  const contactOptions: SelectOption[] = contacts.map((contact) => ({
    value: contact.id,
    label: contact.org ? `${contact.name} (${contact.org})` : contact.name,
  }))
  const contactName = (id: string | null): string | null => {
    if (!id) return null
    return contacts.find((contact) => contact.id === id)?.name ?? "Unknown"
  }

  return (
    <section aria-label="Assets and liabilities">
      <PageHeader
        title="Assets and liabilities"
        description="Everything the estate owns and owes: each asset with its value at the date of death, and each liability outstanding."
      />
      <div className="space-y-10">
        <AssetsSection
          estateId={estateId}
          contactOptions={contactOptions}
          contactName={contactName}
        />
        <LiabilitiesSection
          estateId={estateId}
          contactOptions={contactOptions}
          contactName={contactName}
        />
      </div>
    </section>
  )
}
