/*
  Digital assets module tests over a mocked fetch: the list renders with
  the type badge, login known and recurring amount columns, the recurring
  total stat card shows GET /digital/recurring-total, and creating posts
  the digital asset payload. Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { DigitalAsset } from "./digital-meta"

import DigitalPage from "./index"

const baseRow = {
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  created_by: "executor@example.com",
  archived_at: null,
  archive_reason: null,
}

const records: DigitalAsset[] = [
  {
    ...baseRow,
    id: "g1",
    service: "Example streaming service",
    type: "subscription",
    login_known: true,
    action: "close",
    recurring_amount: "15.99",
    status: "open",
  },
  {
    ...baseRow,
    id: "g2",
    service: "Example email account",
    type: "email",
    login_known: false,
    action: "memorialise",
    recurring_amount: null,
    status: "notified",
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
  "/digital-items": () => json(records),
  "/digital/recurring-total": () => json({ recurring_total: "15.99" }),
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
  return render(<DigitalPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("DigitalPage", () => {
  it("renders the list with type badge, login known and the recurring total", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(
      await screen.findByText("Example streaming service"),
    ).toBeInTheDocument()
    const table = screen.getByRole("table", { name: "Digital assets" })
    expect(within(table).getByText("subscription")).toBeInTheDocument()
    expect(within(table).getByText("Yes")).toBeInTheDocument()
    expect(within(table).getByText("close")).toBeInTheDocument()
    expect(within(table).getByText("£15.99")).toBeInTheDocument()

    expect(screen.getByText("Recurring charges")).toBeInTheDocument()
    expect(await screen.findAllByText("£15.99")).toHaveLength(2)
  })

  it("creates a digital asset with the digital payload", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /digital-items": (body) =>
        json({ ...records[0], ...(body as object), id: "g9" }, 201),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add digital asset" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Service"),
      "Example cloud storage",
    )
    await user.type(within(dialog).getByLabelText(/Type/), "storage")
    await user.click(within(dialog).getByLabelText(/Login known/))
    await user.type(within(dialog).getByLabelText(/Action/), "transfer")
    await user.type(
      within(dialog).getByLabelText(/Recurring amount/),
      "7.99",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Add digital asset" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) => call.method === "POST" && call.path === "/digital-items",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/digital-items",
    )
    expect(post?.body).toEqual({
      estate_id: "e1",
      service: "Example cloud storage",
      type: "storage",
      login_known: true,
      action: "transfer",
      recurring_amount: "7.99",
      status: null,
    })
  })

  it("archives a digital asset with the reason in the JSON body", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "DELETE /digital-items/g2": (body) =>
        json({
          ...records[1],
          archive_reason: (body as { reason: string }).reason,
        }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("Example email account"))
    const detail = await screen.findByRole("dialog")
    await user.click(within(detail).getByRole("button", { name: "Archive" }))

    const archiveDialog = await screen.findByRole("dialog", {
      name: "Archive this digital asset",
    })
    await user.type(
      within(archiveDialog).getByLabelText("Reason for archiving"),
      "Account already closed",
    )
    await user.click(
      within(archiveDialog).getByRole("button", { name: "Archive" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "DELETE" && call.path === "/digital-items/g2",
        ),
      ).toBe(true)
    })
    const del = calls.find(
      (call) => call.method === "DELETE" && call.path === "/digital-items/g2",
    )
    expect(del?.body).toEqual({ reason: "Account already closed" })
  })
})
