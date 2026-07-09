/*
  Tracing module tests over a mocked fetch: the read only completeness
  dashboard renders its sections (stats, official search routes as
  external link cards, estimate basis assets, outstanding debtors and
  unconfirmed holdings). Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import TracingPage from "./index"

const completeness = {
  estimated_value_assets: [
    {
      id: "a1",
      category: "bank_account",
      sub_type: null,
      description: "Example Bank current account",
      dod_value: "1200.00",
      value_basis: "estimate",
    },
  ],
  unnotified_contacts_count: 3,
  outstanding_debtors: [
    {
      id: "d1",
      type: "employer final salary",
      amount_expected: "850.00",
      amount_received: null,
      outstanding: "850.00",
      status: "expected",
    },
  ],
  unconfirmed_unlisted_holdings: [
    {
      id: "a2",
      category: "unlisted_shares",
      sub_type: "club",
      description: "Example flying club share",
      dod_value: null,
      value_basis: "estimate",
    },
  ],
  search_suggestions: [
    {
      name: "My Lost Account",
      url: "https://example.com/mylostaccount",
      covers: "Dormant bank and building society accounts",
    },
    {
      name: "Gretel",
      url: "https://example.com/gretel",
      covers: "Lost pensions and investments",
    },
  ],
  warning:
    "These official searches are free. Never pay a reclaim firm to run them on the estate's behalf.",
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function mockApi(routes: Record<string, () => Response>) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = new URL(String(input))
      const handler = routes[url.pathname]
      return handler ? handler() : json({ detail: "Not found" }, 404)
    }),
  )
}

const defaultRoutes = {
  "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
  "/tracing/completeness": () => json(completeness),
}

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
  return render(<TracingPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("TracingPage", () => {
  it("renders the completeness stats and list sections", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(
      await screen.findByText("Contacts not yet notified"),
    ).toBeInTheDocument()
    expect(screen.getByText("3")).toBeInTheDocument()

    expect(
      screen.getByText("Assets valued on an estimate"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("Example Bank current account"),
    ).toBeInTheDocument()

    expect(screen.getAllByText("Outstanding debtors").length).toBeGreaterThan(0)
    expect(screen.getByText("employer final salary")).toBeInTheDocument()
    expect(screen.getByText("£850.00")).toBeInTheDocument()

    expect(screen.getAllByText("Unconfirmed holdings").length).toBeGreaterThan(0)
    expect(
      screen.getByText("Example flying club share"),
    ).toBeInTheDocument()
  })

  it("renders the official search routes as external link cards", async () => {
    mockApi(defaultRoutes)
    renderPage()

    const section = await screen.findByRole("region", {
      name: "Official search routes",
    })
    const link = within(section).getByRole("link", {
      name: /My Lost Account/,
    })
    expect(link).toHaveAttribute("href", "https://example.com/mylostaccount")
    expect(link).toHaveAttribute("target", "_blank")
    expect(link).toHaveAttribute("rel", "noopener noreferrer")
    expect(within(link).getByText("(opens in a new tab)")).toBeInTheDocument()
    expect(
      within(section).getByText("Dormant bank and building society accounts"),
    ).toBeInTheDocument()
    expect(
      within(section).getByRole("link", { name: /Gretel/ }),
    ).toBeInTheDocument()
    expect(
      within(section).getByText(/These official searches are free/),
    ).toBeInTheDocument()
  })

  it("shows a calm placeholder when the endpoint is not available", async () => {
    mockApi({ "/me": defaultRoutes["/me"] })
    renderPage()

    expect(
      await screen.findByText(/completeness summary is not available yet/),
    ).toBeInTheDocument()
  })
})
