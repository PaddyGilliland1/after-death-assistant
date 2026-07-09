/*
  Assets and liabilities module tests over a mocked fetch: both registers
  render, the create flow POSTs the AssetCreate payload with empty
  optionals omitted, the detail dialog shows the valuation history, and a
  viewer sees the tables without any write affordances.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import AssetsPage from "./index"

const ESTATE_ID = "0e585ba8-9f4d-4f0e-a5b7-000000000001"

const estate = { id: ESTATE_ID, name: "Estate of Alex Example" }

const audit = {
  estate_id: ESTATE_ID,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  created_by: "alex.example@example.com",
  archived_at: null,
  archive_reason: null,
}

const contacts = [
  {
    id: "c1",
    ...audit,
    kind: "org",
    category: "bank",
    name: "Example Bank",
    org: null,
    relationship: null,
    email: null,
    phone: null,
    address: null,
    references: [],
    holds_or_handles: null,
    notify_required: true,
    notification_status: null,
    notified_date: null,
    notified_method: null,
  },
]

const assets = [
  {
    id: "a1",
    ...audit,
    category: "bank_account",
    sub_type: null,
    description: "Current account",
    holder_contact_id: "c1",
    account_reference: "00-11-22 12345678",
    ownership: "sole",
    tic_share_pct: null,
    dod_value: "12500.00",
    value_basis: "confirmed",
    valuation_source: "closing statement",
    valuation_date: "2026-01-05",
    current_or_realised_value: "12600.00",
    realised_date: null,
    income_since_death: null,
    iht_schedule: "IHT406",
    rnrb_qualifying: false,
    passes_outside_estate: false,
    status: "notified",
  },
]

const liabilities = [
  {
    id: "l1",
    ...audit,
    type: "credit_card",
    creditor_contact_id: "c1",
    amount: "430.00",
    as_at_date: "2026-01-15",
    status: "outstanding",
    iht_deductible: true,
  },
]

const valuations = [
  {
    id: "v1",
    ...audit,
    asset_id: "a1",
    value: "12750.00",
    basis: "estimate",
    source: "online balance",
    date: "2026-02-01",
  },
]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type Handler = (body: unknown) => Response

function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname
      const method = init?.method ?? "GET"
      const handler = routes[`${method} ${path}`]
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      return handler ? handler(body) : json({ detail: "Not found" }, 404)
    },
  )
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

function baseRoutes(role: "executor" | "viewer" = "executor") {
  return {
    "GET /me": () => json({ email: "alex.example@example.com", role }),
    "GET /estate": () => json(estate),
    "GET /contacts": () => json(contacts),
    "GET /assets": () => json(assets),
    "GET /liabilities": () => json(liabilities),
    "GET /assets/a1/valuations": () => json(valuations),
  } satisfies Record<string, Handler>
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
  return render(<AssetsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AssetsPage", () => {
  it("renders the assets and liabilities registers", async () => {
    mockApi(baseRoutes())
    renderPage()

    expect(await screen.findByText("Current account")).toBeInTheDocument()
    expect(screen.getByText("£12,500.00")).toBeInTheDocument()
    expect(screen.getByText("£12,600.00")).toBeInTheDocument()
    expect(screen.getAllByText("Example Bank").length).toBeGreaterThan(0)
    expect(await screen.findByText("Credit card")).toBeInTheDocument()
    expect(screen.getByText("£430.00")).toBeInTheDocument()
  })

  it("creates an asset with the AssetCreate payload, omitting empty optionals", async () => {
    const created = { ...assets[0], id: "a2", description: "Savings account" }
    const routes = baseRoutes()
    const postAsset = vi.fn((body: unknown) => {
      void body
      return json(created, 201)
    })
    mockApi({ ...routes, "POST /assets": postAsset })

    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add asset" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Description"),
      "Savings account",
    )
    await user.selectOptions(
      within(dialog).getByLabelText("Category"),
      "savings",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Save asset" }),
    )

    await waitFor(() => expect(postAsset).toHaveBeenCalledTimes(1))
    expect(postAsset).toHaveBeenCalledWith({
      estate_id: ESTATE_ID,
      description: "Savings account",
      category: "savings",
      ownership: "sole",
      value_basis: "estimate",
      rnrb_qualifying: false,
      passes_outside_estate: false,
    })
  })

  it("shows every field and the valuation history in the detail dialog", async () => {
    mockApi(baseRoutes())
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    await user.click(await screen.findByText("Current account"))
    const dialog = await screen.findByRole("dialog")

    expect(
      within(dialog).getByText("Valuation history"),
    ).toBeInTheDocument()
    expect(await within(dialog).findByText("£12,750.00")).toBeInTheDocument()
    expect(within(dialog).getByText(/online balance/)).toBeInTheDocument()
    expect(within(dialog).getByText("IHT406")).toBeInTheDocument()
    expect(
      within(dialog).getByRole("button", { name: "Add valuation" }),
    ).toBeInTheDocument()
  })

  it("adds a valuation with POST /assets/{id}/valuations", async () => {
    const routes = baseRoutes()
    const postValuation = vi.fn(() =>
      json({ ...valuations[0], id: "v2" }, 201),
    )
    mockApi({ ...routes, "POST /assets/a1/valuations": postValuation })

    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    await user.click(await screen.findByText("Current account"))
    const dialog = await screen.findByRole("dialog")
    await within(dialog).findByText("£12,750.00")

    await user.type(within(dialog).getByLabelText(/^Value/), "13000.00")
    fireEvent.change(within(dialog).getByLabelText(/Valuation date/), {
      target: { value: "2026-07-01" },
    })
    await user.click(
      within(dialog).getByRole("button", { name: "Add valuation" }),
    )

    await waitFor(() => expect(postValuation).toHaveBeenCalledTimes(1))
    expect(postValuation).toHaveBeenCalledWith({
      value: "13000.00",
      basis: "estimate",
      date: "2026-07-01",
    })
  })

  it("hides every write affordance from a viewer", async () => {
    mockApi(baseRoutes("viewer"))
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    expect(await screen.findByText("Current account")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Add asset" }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Add liability" }),
    ).not.toBeInTheDocument()

    await user.click(screen.getByText("Current account"))
    const dialog = await screen.findByRole("dialog")

    expect(
      within(dialog).queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument()
    expect(
      within(dialog).queryByRole("button", { name: "Archive" }),
    ).not.toBeInTheDocument()
    expect(
      within(dialog).queryByRole("button", { name: "Add valuation" }),
    ).not.toBeInTheDocument()
    expect(await within(dialog).findByText("£12,750.00")).toBeInTheDocument()
  })
})
