/*
  Costs module tests over a mocked fetch: the list renders with money,
  reimbursement and IHT treatment columns, creating posts the CostCreate
  payload, and the "By type" section renders the stored totals from
  GET /costs/by-type. Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { Cost } from "@/lib/types"

import CostsPage from "./index"

const baseRow = {
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  created_by: "executor@example.com",
  archived_at: null,
  archive_reason: null,
}

const costs: Cost[] = [
  {
    ...baseRow,
    id: "k1",
    description: "Funeral director invoice",
    category: "funeral",
    amount: "3500.00",
    vat: "700.00",
    date: "2026-06-10",
    paid_by: "executor@example.com",
    payment_method: "card",
    reimbursable: true,
    reimbursed: false,
    reimbursed_date: null,
    iht_treatment: "funeral_deductible",
    receipt_document_id: null,
    executor_private: false,
  },
  {
    ...baseRow,
    id: "k2",
    description: "Probate application fee",
    category: "probate",
    amount: "300.00",
    vat: null,
    date: "2026-06-20",
    paid_by: null,
    payment_method: null,
    reimbursable: false,
    reimbursed: false,
    reimbursed_date: null,
    iht_treatment: "admin_not_deductible",
    receipt_document_id: null,
    executor_private: false,
  },
]

const byType = {
  by_category: [
    { category: "funeral", total: "3500.00" },
    { category: "probate", total: "300.00" },
  ],
  by_iht_treatment: [
    { iht_treatment: "funeral_deductible", total: "3500.00" },
    { iht_treatment: "admin_not_deductible", total: "300.00" },
  ],
}

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

const defaultRoutes = {
  "/me": () => json({ email: "executor@example.com", role: "executor" }),
  "/estate": () => json({ id: "e1", name: "Example Estate" }),
  "/costs": () => json(costs),
  "/costs/by-type": () => json(byType),
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
  return render(<CostsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("CostsPage", () => {
  it("renders the costs list with money and treatment columns", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(
      await screen.findByText("Funeral director invoice"),
    ).toBeInTheDocument()
    expect(screen.getByText("Probate application fee")).toBeInTheDocument()
    const table = screen.getByRole("table", { name: "Costs" })
    expect(within(table).getByText("£3,500.00")).toBeInTheDocument()
    expect(within(table).getByText("£700.00")).toBeInTheDocument()
    expect(within(table).getByText("Reimbursable")).toBeInTheDocument()
    expect(
      within(table).getByText("Funeral (deductible)"),
    ).toBeInTheDocument()
    expect(within(table).getByText("10 Jun 2026")).toBeInTheDocument()
  })

  it("creates a cost with the CostCreate payload", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /costs": (body) =>
        json({ ...costs[1], ...(body as object), id: "k9" }, 201),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("button", { name: "Add cost" }))
    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Description"),
      "Property valuation",
    )
    await user.type(within(dialog).getByLabelText("Category"), "valuation")
    await user.type(within(dialog).getByLabelText(/Amount/), "180.00")
    await user.type(within(dialog).getByLabelText("Date"), "2026-06-25")
    await user.click(within(dialog).getByLabelText(/Reimbursable/))
    await user.selectOptions(
      within(dialog).getByLabelText("IHT treatment"),
      "admin_not_deductible",
    )
    await user.click(within(dialog).getByRole("button", { name: "Add cost" }))

    await waitFor(() => {
      expect(
        calls.some((call) => call.method === "POST" && call.path === "/costs"),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/costs",
    )
    expect(post?.body).toEqual({
      estate_id: "e1",
      description: "Property valuation",
      category: "valuation",
      amount: "180.00",
      vat: null,
      date: "2026-06-25",
      paid_by: null,
      payment_method: null,
      reimbursable: true,
      reimbursed: false,
      reimbursed_date: null,
      iht_treatment: "admin_not_deductible",
      executor_private: false,
    })
  })

  it("renders the by-type summary of stored totals", async () => {
    mockApi(defaultRoutes)
    renderPage()

    const section = (await screen.findByRole("region", {
      name: "Costs by type",
    })) as HTMLElement
    expect(
      within(section).getByText(/Totals are sums of recorded costs/),
    ).toBeInTheDocument()

    const categoryTable = await within(section).findByRole("table", {
      name: "Category",
    })
    expect(within(categoryTable).getByText("funeral")).toBeInTheDocument()
    expect(within(categoryTable).getByText("£3,500.00")).toBeInTheDocument()
    expect(within(categoryTable).getByText("£300.00")).toBeInTheDocument()

    const treatmentTable = within(section).getByRole("table", {
      name: "IHT treatment",
    })
    expect(
      within(treatmentTable).getByText("Funeral (deductible)"),
    ).toBeInTheDocument()
    expect(
      within(treatmentTable).getByText("Administration (not deductible)"),
    ).toBeInTheDocument()
    expect(within(treatmentTable).getByText("£3,500.00")).toBeInTheDocument()
  })

  it("archives a cost with a reason from the detail dialog", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "DELETE /costs/k2": (body) =>
        json({ ...costs[1], archive_reason: (body as { reason: string }).reason }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("Probate application fee"))
    const detail = await screen.findByRole("dialog")
    await user.click(within(detail).getByRole("button", { name: "Archive" }))

    const archiveDialog = await screen.findByRole("dialog", {
      name: "Archive this cost",
    })
    await user.type(
      within(archiveDialog).getByLabelText("Reason for archiving"),
      "Recorded twice in error",
    )
    await user.click(
      within(archiveDialog).getByRole("button", { name: "Archive" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "DELETE" && call.path.startsWith("/costs/k2"),
        ),
      ).toBe(true)
    })
    const del = calls.find(
      (call) =>
        call.method === "DELETE" && call.path.startsWith("/costs/k2"),
    )
    expect(del?.body).toEqual({ reason: "Recorded twice in error" })
  })
})
