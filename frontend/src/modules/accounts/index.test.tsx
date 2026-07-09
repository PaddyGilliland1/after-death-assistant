/*
  Estate accounts tests over a mocked fetch: the trial balance renders
  with figures exactly as returned, the reconciliation line follows
  is_balanced, the donut ships its hidden data table fallback, and the
  page degrades calmly when the backend has no accounts yet.

  The ECharts React wrapper is mocked: jsdom cannot lay out or render
  SVG charts, and the accessible contract under test is the fallback
  table, not the drawing.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, within } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("echarts-for-react/lib/core", () => ({
  default: () => <div data-testid="echarts-donut" />,
}))

import AccountsPage from "./index"

const accounts = {
  net_estate: "500000.00",
  capital_account: "498500.00",
  income_account: "1200.50",
  administration_account: "70000.00",
  legacies_total: "10000.00",
  residue: "421200.50",
  distribution_account: "431200.50",
  distributions: [
    {
      beneficiary_id: "b1",
      residuary_share: "0.5",
      entitlement: "210600.25",
      interim_received: "9500.00",
      remaining_due: "201100.25",
    },
    {
      beneficiary_id: "b2",
      residuary_share: "0.5",
      entitlement: "210600.25",
      interim_received: "0.00",
      remaining_due: "210600.25",
    },
  ],
  is_balanced: true,
}

// Synthetic contact names only; no personal data in fixtures.
const contacts = [
  { id: "b1", name: "Beneficiary One" },
  { id: "b2", name: "Beneficiary Two" },
]

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
      const path = new URL(String(input)).pathname
      const handler = routes[path]
      return handler ? handler() : json({ detail: "Not found" }, 404)
    }),
  )
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
  return render(<AccountsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AccountsPage", () => {
  it("renders the trial balance and headline figures exactly as returned", async () => {
    mockApi({
      "/estate/accounts": () => json(accounts),
      "/contacts": () => json(contacts),
    })
    renderPage()

    // Headline stat cards.
    expect(await screen.findByText("£500,000.00")).toBeInTheDocument()
    expect(screen.getByText("Net estate")).toBeInTheDocument()
    expect(screen.getByText("Residue")).toBeInTheDocument()
    expect(screen.getByText("£421,200.50")).toBeInTheDocument()
    expect(screen.getByText("Legacies total")).toBeInTheDocument()
    expect(screen.getByText("£10,000.00")).toBeInTheDocument()

    // Four-account trial balance, pence preserved.
    expect(screen.getByText("Capital account")).toBeInTheDocument()
    expect(screen.getByText("£498,500.00")).toBeInTheDocument()
    expect(screen.getByText("Income account")).toBeInTheDocument()
    expect(screen.getByText("£1,200.50")).toBeInTheDocument()
    expect(screen.getByText("Administration account")).toBeInTheDocument()
    expect(screen.getByText("£70,000.00")).toBeInTheDocument()
    expect(screen.getByText("Distribution account")).toBeInTheDocument()
    expect(screen.getByText("£431,200.50")).toBeInTheDocument()

    // Distribution table with beneficiary names, shares and money.
    const table = screen.getByRole("table", {
      name: "Residuary distributions",
    })
    expect(within(table).getByText("Beneficiary One")).toBeInTheDocument()
    expect(within(table).getByText("Beneficiary Two")).toBeInTheDocument()
    expect(within(table).getAllByText("50%").length).toBe(2)
    expect(within(table).getAllByText("£210,600.25").length).toBeGreaterThan(0)
    expect(within(table).getByText("£201,100.25")).toBeInTheDocument()
    expect(within(table).getByText("£9,500.00")).toBeInTheDocument()
  })

  it("shows the green reconciliation line when the accounts balance", async () => {
    mockApi({
      "/estate/accounts": () => json(accounts),
      "/contacts": () => json(contacts),
    })
    renderPage()

    const status = await screen.findByRole("status")
    expect(status).toHaveTextContent("Accounts reconcile.")
  })

  it("shows an alert with advice when the accounts do not balance", async () => {
    mockApi({
      "/estate/accounts": () => json({ ...accounts, is_balanced: false }),
      "/contacts": () => json(contacts),
    })
    renderPage()

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("Accounts do not reconcile.")
    expect(alert).toHaveTextContent("Check the most recent entries")
  })

  it("renders the donut with a visually hidden data table fallback", async () => {
    mockApi({
      "/estate/accounts": () => json(accounts),
      "/contacts": () => json(contacts),
    })
    renderPage()

    expect(await screen.findByTestId("echarts-donut")).toBeInTheDocument()
    expect(
      screen.getByRole("img", { name: /donut chart of residuary shares/i }),
    ).toBeInTheDocument()

    const fallback = screen.getByRole("table", {
      name: "Residuary shares by beneficiary",
    })
    expect(within(fallback).getByText("Beneficiary One")).toBeInTheDocument()
    expect(within(fallback).getByText("Beneficiary Two")).toBeInTheDocument()
    expect(within(fallback).getAllByText("50%").length).toBe(2)
  })

  it("degrades calmly when the backend has no accounts endpoint yet", async () => {
    mockApi({})
    renderPage()

    expect(await screen.findByRole("status")).toHaveTextContent(
      "The estate accounts are not available yet.",
    )
    expect(screen.queryByRole("alert")).not.toBeInTheDocument()
  })
})
