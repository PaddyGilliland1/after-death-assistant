/*
  Administration tax module tests over a mocked fetch: the per-year card
  renders the income total, complex estate badge with its triggers, ISA
  exemption end and the disposals table with derived 60 day deadlines and
  basis citations; adding a disposal patches the year record's JSON list.
  Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { AdminTaxYear } from "./admin-tax-meta"

import AdminTaxPage from "./index"

const baseRow = {
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  created_by: "executor@example.com",
  archived_at: null,
  archive_reason: null,
}

const years: AdminTaxYear[] = [
  {
    ...baseRow,
    id: "y1",
    tax_year: "2025-26",
    income_total: "4200.00",
    estate_complex: true,
    complex_reasons: ["estate value exceeds £2.5 million"],
    isa_exemption_end: "2029-03-01",
    cgt_disposals: [
      {
        description: "Sale of 12 Example Street",
        disposal_date: "2026-05-10",
        proceeds: "250000.00",
        gain: "12000.00",
      },
    ],
    cgt_60day_deadlines: [
      {
        disposal_date: "2026-05-10",
        deadline: "2026-07-09",
        basis: "TCGA 1992 Sch 2, 60 days from completion",
      },
    ],
  },
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

const defaultRoutes = {
  "/me": () => json({ email: "executor@example.com", role: "executor" }),
  "/estate": () => json({ id: "e1", name: "Example Estate" }),
  "/admin-tax": () => json(years),
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
  return render(<AdminTaxPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AdminTaxPage", () => {
  it("renders the year card with income, complex badge, ISA end and deadlines", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(await screen.findByText("Tax year 2025-26")).toBeInTheDocument()
    expect(screen.getByText("Complex estate")).toBeInTheDocument()
    expect(
      screen.getByText(/estate value exceeds £2.5 million/),
    ).toBeInTheDocument()
    expect(screen.getByText("£4,200.00")).toBeInTheDocument()
    expect(screen.getByText("1 Mar 2029")).toBeInTheDocument()

    const table = screen.getByRole("table", { name: "Disposals in 2025-26" })
    expect(
      within(table).getByText("Sale of 12 Example Street"),
    ).toBeInTheDocument()
    expect(within(table).getByText("10 May 2026")).toBeInTheDocument()
    expect(within(table).getByText("9 Jul 2026")).toBeInTheDocument()
    expect(
      within(table).getByText("TCGA 1992 Sch 2, 60 days from completion"),
    ).toBeInTheDocument()
  })

  it("adds a disposal by patching the year's disposals list", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "PATCH /admin-tax/y1": (body) =>
        json({ ...years[0], ...(body as object) }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add disposal" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Description"),
      "Sale of Example plc shares",
    )
    await user.type(
      within(dialog).getByLabelText("Disposal date"),
      "2026-06-15",
    )
    await user.type(within(dialog).getByLabelText(/Proceeds/), "8000.00")
    await user.click(
      within(dialog).getByRole("button", { name: "Add disposal" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "PATCH" && call.path === "/admin-tax/y1",
        ),
      ).toBe(true)
    })
    const patch = calls.find(
      (call) => call.method === "PATCH" && call.path === "/admin-tax/y1",
    )
    expect(patch?.body).toEqual({
      cgt_disposals: [
        years[0].cgt_disposals[0],
        {
          description: "Sale of Example plc shares",
          disposal_date: "2026-06-15",
          proceeds: "8000.00",
          gain: null,
        },
      ],
    })
  })

  it("creates a tax year with the year payload", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /admin-tax": (body) =>
        json({ ...years[0], ...(body as object), id: "y2" }, 201),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add tax year" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.type(within(dialog).getByLabelText("Tax year"), "2026-27")
    await user.type(within(dialog).getByLabelText(/Income total/), "1500.00")
    await user.click(
      within(dialog).getByRole("button", { name: "Add tax year" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) => call.method === "POST" && call.path === "/admin-tax",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/admin-tax",
    )
    expect(post?.body).toEqual({
      estate_id: "e1",
      tax_year: "2026-27",
      income_total: "1500.00",
      cgt_disposals: [],
    })
  })
})
