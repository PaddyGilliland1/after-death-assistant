/*
  When you need help page tests: the static directory renders every
  group, phone numbers are tel: links so they work from a phone, the
  online-only entries say so, and the verification note is present.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import { HELP_GROUPS } from "./help-contacts"
import HelpPage from "./index"

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function renderPage() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => json({ email: "viewer@example.com", role: "viewer" })),
  )
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
  return render(<HelpPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("HelpPage", () => {
  it("renders every group with all its contacts", () => {
    renderPage()

    for (const group of HELP_GROUPS) {
      const list = screen.getByRole("list", { name: group.heading })
      for (const contact of group.contacts) {
        expect(within(list).getByText(contact.name)).toBeInTheDocument()
      }
    }
  })

  it("offers phone numbers as tel links and marks online-only entries", () => {
    renderPage()

    const samaritans = screen.getByRole("link", { name: /116 123/ })
    expect(samaritans).toHaveAttribute("href", "tel:116123")

    const probate = screen.getByRole("link", { name: /0300 303 0648/ })
    expect(probate).toHaveAttribute("href", "tel:03003030648")

    expect(screen.getAllByText("Online only").length).toBeGreaterThan(0)
  })

  it("says when the numbers were checked", () => {
    renderPage()

    expect(
      screen.getByText(/checked against each organisation's own website on/i),
    ).toBeInTheDocument()
  })
})
