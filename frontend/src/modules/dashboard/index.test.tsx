/*
  Dashboard tests over a mocked fetch: stats from /estate/summary, unread
  alerts from /notifications and upcoming dates from /deadlines, plus the
  graceful state when the backend has none of it yet.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { MemoryRouter } from "react-router-dom"
import { render, screen } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"

import DashboardPage from "./index"

const summary = {
  gross_assets_at_dod: "512000.00",
  net_estate: "448000.00",
  iht_due: "70000.00",
  open_task_count: 4,
  unnotified_contact_count: 2,
  costs_total: "3500.00",
}

const notifications = [
  {
    id: "n1",
    estate_id: "e1",
    user_id: "alex.example@example.com",
    event_type: "cost_recorded",
    entity_ref: "cost:c1",
    message: "A cost of £120.00 was recorded by Alex Example.",
    read_at: null,
    created_at: "2026-07-01T10:00:00Z",
    updated_at: "2026-07-01T10:00:00Z",
    created_by: "system",
    archived_at: null,
    archive_reason: null,
  },
  {
    id: "n2",
    estate_id: "e1",
    user_id: "alex.example@example.com",
    event_type: "asset_added",
    entity_ref: "asset:a1",
    message: "An asset was added earlier.",
    read_at: "2026-07-02T09:00:00Z",
    created_at: "2026-07-01T09:00:00Z",
    updated_at: "2026-07-02T09:00:00Z",
    created_by: "system",
    archived_at: null,
    archive_reason: null,
  },
]

const deadlines = [
  {
    id: "d1",
    estate_id: "e1",
    type: "iht_payment",
    derived_date: "2099-08-31",
    reminders: [],
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    created_by: "system",
    archived_at: null,
    archive_reason: null,
  },
  {
    id: "d2",
    estate_id: "e1",
    type: "creditor_claim",
    derived_date: "2020-01-31",
    reminders: [],
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
    created_by: "system",
    archived_at: null,
    archive_reason: null,
  },
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

function renderDashboard() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      </MemoryRouter>
    )
  }
  return render(<DashboardPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("DashboardPage", () => {
  it("renders the six estate statistics from the summary", async () => {
    mockApi({
      "/estate/summary": () => json(summary),
      "/notifications": () => json([]),
      "/deadlines": () => json([]),
    })
    renderDashboard()

    expect(await screen.findByText("£512,000.00")).toBeInTheDocument()
    expect(screen.getByText("£448,000.00")).toBeInTheDocument()
    expect(screen.getByText("£70,000.00")).toBeInTheDocument()
    expect(screen.getByText("£3,500.00")).toBeInTheDocument()
    expect(screen.getByText("Open tasks")).toBeInTheDocument()
    expect(screen.getByText("4")).toBeInTheDocument()
    expect(screen.getByText("Contacts to notify")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
  })

  it("lists only unread notifications in the alerts card", async () => {
    mockApi({
      "/estate/summary": () => json(summary),
      "/notifications": () => json(notifications),
      "/deadlines": () => json([]),
    })
    renderDashboard()

    expect(
      await screen.findByText("A cost of £120.00 was recorded by Alex Example."),
    ).toBeInTheDocument()
    expect(
      screen.queryByText("An asset was added earlier."),
    ).not.toBeInTheDocument()
  })

  it("shows upcoming deadlines soonest first and flags overdue ones", async () => {
    mockApi({
      "/estate/summary": () => json(summary),
      "/notifications": () => json([]),
      "/deadlines": () => json(deadlines),
    })
    renderDashboard()

    expect(await screen.findByText("Creditor claim")).toBeInTheDocument()
    expect(screen.getByText("Iht payment")).toBeInTheDocument()
    expect(screen.getByText("31 Jan 2020")).toBeInTheDocument()
    expect(screen.getByText("Overdue")).toBeInTheDocument()
  })

  it("degrades calmly when the backend has no endpoints yet", async () => {
    mockApi({})
    renderDashboard()

    expect(await screen.findByRole("status")).toHaveTextContent(
      "The estate summary is not available yet.",
    )
    expect(screen.getAllByText("Not yet available").length).toBe(6)
    expect(
      await screen.findByText(/Alerts are not available yet/),
    ).toBeInTheDocument()
    expect(
      await screen.findByText(/Deadlines are not available yet/),
    ).toBeInTheDocument()
  })
})
