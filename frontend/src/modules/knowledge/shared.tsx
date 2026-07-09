/*
  Small presentational pieces shared by the knowledge sections: an
  external link with the right semantics, and the licence and fetch date
  attribution line required for cached official content.
*/

import type * as React from "react"
import { ExternalLink } from "lucide-react"

import { formatDate } from "@/components/shared/formatters"

import { isOgl, OGL_LINE } from "./knowledge-meta"

export function ExternalTextLink({
  href,
  children,
}: {
  href: string
  children: React.ReactNode
}) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 underline underline-offset-4 hover:text-foreground/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
    >
      {children}
      <ExternalLink
        aria-hidden="true"
        className="size-3.5 shrink-0 text-muted-foreground"
      />
      <span className="sr-only">(opens in a new tab)</span>
    </a>
  )
}

export function LicenceLine({
  licence,
  fetchDate,
}: {
  licence: string | null | undefined
  fetchDate: string | null | undefined
}) {
  const licenceText = isOgl(licence) ? OGL_LINE : (licence ?? "")
  const fetched = fetchDate ? `Fetched ${formatDate(fetchDate)}.` : ""
  const text = [licenceText, fetched].filter(Boolean).join(" ")
  if (!text) return null
  return <p className="text-xs text-muted-foreground">{text}</p>
}
