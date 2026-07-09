/*
  Knowledge library module: cached HMRC forms and official guidance in
  three parts. Search finds matching chunks, Library lists the cached
  documents with their extracted text, and Ask answers questions with
  numbered citations to the cached sources. Ingest is admin only and
  lives in the Library section.
*/

import * as React from "react"

import { PageHeader } from "@/components/shared/page-header"
import { useMe } from "@/lib/auth"
import { cn } from "@/lib/utils"

import { AskSection } from "./ask-section"
import { GUIDANCE_DISCLAIMER } from "./knowledge-meta"
import { LibrarySection } from "./library-section"
import { SearchSection } from "./search-section"

const TABS = [
  { id: "search", label: "Search" },
  { id: "library", label: "Library" },
  { id: "ask", label: "Ask" },
] as const

type TabId = (typeof TABS)[number]["id"]

export default function KnowledgePage() {
  const { role } = useMe()
  const isAdmin = role === "admin"

  const [active, setActive] = React.useState<TabId>("search")
  const baseId = React.useId()
  const tabRefs = React.useRef(new Map<TabId, HTMLButtonElement>())

  function focusTab(id: TabId) {
    setActive(id)
    tabRefs.current.get(id)?.focus()
  }

  function handleKeyDown(event: React.KeyboardEvent, index: number) {
    const count = TABS.length
    if (event.key === "ArrowRight") {
      event.preventDefault()
      focusTab(TABS[(index + 1) % count].id)
    } else if (event.key === "ArrowLeft") {
      event.preventDefault()
      focusTab(TABS[(index - 1 + count) % count].id)
    } else if (event.key === "Home") {
      event.preventDefault()
      focusTab(TABS[0].id)
    } else if (event.key === "End") {
      event.preventDefault()
      focusTab(TABS[count - 1].id)
    }
  }

  return (
    <section aria-label="Knowledge library">
      <PageHeader
        title="Knowledge library"
        description="Cached HMRC forms and official guidance, with cited answers to your questions."
      />

      <p className="mb-6 max-w-prose text-sm text-muted-foreground">
        {GUIDANCE_DISCLAIMER}
      </p>

      <div
        role="tablist"
        aria-label="Knowledge sections"
        className="mb-6 flex gap-1 border-b"
      >
        {TABS.map((tab, index) => {
          const isActive = active === tab.id
          return (
            <button
              key={tab.id}
              ref={(node) => {
                if (node) tabRefs.current.set(tab.id, node)
                else tabRefs.current.delete(tab.id)
              }}
              type="button"
              role="tab"
              id={`${baseId}-tab-${tab.id}`}
              aria-selected={isActive}
              aria-controls={`${baseId}-panel-${tab.id}`}
              tabIndex={isActive ? 0 : -1}
              onClick={() => setActive(tab.id)}
              onKeyDown={(event) => handleKeyDown(event, index)}
              className={cn(
                "-mb-px rounded-t-md border-b-2 px-4 py-2 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                isActive
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground",
              )}
            >
              {tab.label}
            </button>
          )
        })}
      </div>

      {TABS.map((tab) => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`${baseId}-panel-${tab.id}`}
          aria-labelledby={`${baseId}-tab-${tab.id}`}
          hidden={active !== tab.id}
          tabIndex={0}
          className="focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
        >
          {tab.id === "search" ? (
            <SearchSection />
          ) : tab.id === "library" ? (
            <LibrarySection isAdmin={isAdmin} />
          ) : (
            <AskSection />
          )}
        </div>
      ))}
    </section>
  )
}
