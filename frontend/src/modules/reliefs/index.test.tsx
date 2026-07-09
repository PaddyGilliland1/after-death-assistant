/*
  Reliefs module tests over a mocked fetch: the list renders with the type
  badge, linked asset, deadline and reclaim columns, the watchlist banner
  flags windows closing within 90 days, creating posts the relief payload,
  and archiving sends the reason in the JSON body. Fixtures use
  example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { Relief, ReliefWatchlistItem } from "./relief-meta"

import ReliefsPage from "./index"

const baseRow = {
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  created_by: "executor@example.com",
  archived_at: null,
  archive_reason: null,
}

function isoInDays(days: number): string {
  const date = new Date()
  date.setDate(date.getDate() + days)
  return date.toISOString().slice(0, 10)
}

const soonDeadline = isoInDays(30)

const reliefs: Relief[] = [
  {
    ...baseRow,
    id: "r1",
    relief_type: "iht38",
    asset_id: "a1",
    probate_value: "250000.00",
    sale_value: "230000.00",
    sale_date: "2026-05-01",
    window_deadline: soonDeadline,
    window_basis: "IHTA 1984 s.191, four years from death",
    potential_reclaim: "20000.00",
    status: "monitoring",
  },
  {
    ...baseRow,
    id: "r2",
    relief_type: "iht35",
    asset_id: null,
    probate_value: "10000.00",
    sale_value: null,
    sale_date: null,
    window_deadline: "2020-01-01",
    window_basis: "IHTA 1984 s.179, twelve months from death",
    potential_reclaim: null,
    status: null,
  },
]

const assets = [
  { ...baseRow, id: "a1", description: "12 Example Street" },
  { ...baseRow, id: "a2", description: "Example plc shares" },
]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

interface RecordedCall {
  method: string
  path: string
  body: unknown
}

function mockApi(
  routes: Record<string, (body: unknown) => Response>,
): RecordedCall[] {
  const calls: RecordedCall[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const path = url.pathname + url.search
      const method = init?.method ?? "GET"
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ method, path, body })
      const handler =
        routes[`${method} ${url.pathname}`] ?? routes[url.pathname]
      return handler ? handler(body) : json({ detail: "Not found" }, 404)
    }),
  )
  return calls
}

const watchlist: ReliefWatchlistItem[] = [
  {
    id: "r1",
    estate_id: "e1",
    relief_type: "iht38",
    asset_id: "a1",
    window_deadline: soonDeadline,
    days_remaining: 30,
    potential_reclaim: "20000.00",
    status: "monitoring",
  },
]

const defaultRoutes = {
  "/me": () => json({ email: "executor@example.com", role: "executor" }),
  "/estate": () => json({ id: "e1", name: "Example Estate" }),
  "/assets": () => json(assets),
  "/reliefs": () => json(reliefs),
  "/reliefs/watchlist": () => json(watchlist),
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
  return render(<ReliefsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ReliefsPage", () => {
  it("renders the reliefs list with type, asset, values and overdue badge", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(await screen.findByText("IHT38 land")).toBeInTheDocument()
    const table = screen.getByRole("table", { name: "Reliefs" })
    expect(within(table).getByText("IHT35 shares")).toBeInTheDocument()
    expect(within(table).getByText("12 Example Street")).toBeInTheDocument()
    expect(within(table).getByText("£250,000.00")).toBeInTheDocument()
    expect(within(table).getByText("£20,000.00")).toBeInTheDocument()
    expect(within(table).getByText("1 Jan 2020")).toBeInTheDocument()
    expect(within(table).getByText("Overdue")).toBeInTheDocument()
  })

  it("shows the watchlist banner for windows closing within 90 days", async () => {
    mockApi(defaultRoutes)
    renderPage()

    const banner = await screen.findByRole("status")
    expect(
      within(banner).getByText("Relief windows closing within 90 days"),
    ).toBeInTheDocument()
    expect(
      within(banner).getByText(/IHT38 loss on sale of land: deadline/),
    ).toBeInTheDocument()
  })

  it("creates a relief with the relief payload", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /reliefs": (body) =>
        json({ ...reliefs[0], ...(body as object), id: "r9" }, 201),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add relief" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.selectOptions(
      within(dialog).getByLabelText("Relief type"),
      "iht35",
    )
    await user.selectOptions(
      within(dialog).getByLabelText(/Linked asset/),
      "a2",
    )
    await user.type(
      within(dialog).getByLabelText(/Probate value/),
      "15000.00",
    )
    await user.type(within(dialog).getByLabelText(/Sale value/), "12000.00")
    await user.type(
      within(dialog).getByLabelText(/Window deadline/),
      "2027-03-01",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Add relief" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) => call.method === "POST" && call.path === "/reliefs",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/reliefs",
    )
    expect(post?.body).toEqual({
      estate_id: "e1",
      relief_type: "iht35",
      asset_id: "a2",
      probate_value: "15000.00",
      sale_value: "12000.00",
      sale_date: null,
      window_deadline: "2027-03-01",
      potential_reclaim: null,
      status: null,
    })
  })

  it("archives a relief with the reason in the JSON body", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "DELETE /reliefs/r2": (body) =>
        json({
          ...reliefs[1],
          archive_reason: (body as { reason: string }).reason,
        }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("IHT35 shares"))
    const detail = await screen.findByRole("dialog")
    await user.click(within(detail).getByRole("button", { name: "Archive" }))

    const archiveDialog = await screen.findByRole("dialog", {
      name: "Archive this relief",
    })
    await user.type(
      within(archiveDialog).getByLabelText("Reason for archiving"),
      "Recorded in error",
    )
    await user.click(
      within(archiveDialog).getByRole("button", { name: "Archive" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "DELETE" && call.path === "/reliefs/r2",
        ),
      ).toBe(true)
    })
    const del = calls.find(
      (call) => call.method === "DELETE" && call.path === "/reliefs/r2",
    )
    expect(del?.body).toEqual({ reason: "Recorded in error" })
  })
})
