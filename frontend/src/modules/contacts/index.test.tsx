/*
  Contacts module tests over a mocked fetch: the list renders with its
  notification columns, the To notify preset filters, creating posts the
  ContactCreate payload, and the Mark notified quick action patches the
  notification tracker fields. Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { Contact } from "@/lib/types"

import ContactsPage from "./index"

const baseRow = {
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  created_by: "executor@example.com",
  archived_at: null,
  archive_reason: null,
}

const contacts: Contact[] = [
  {
    ...baseRow,
    id: "c1",
    kind: "org",
    category: "bank",
    name: "Example Bank",
    org: "Example Bank plc",
    relationship: "Current account provider",
    email: "bereavement@examplebank.example.com",
    phone: null,
    address: null,
    references: ["REF-100"],
    holds_or_handles: "Current account",
    notify_required: true,
    notification_status: "pending",
    notified_date: null,
    notified_method: null,
  },
  {
    ...baseRow,
    id: "c2",
    kind: "org",
    category: "solicitor",
    name: "Example Solicitors",
    org: "Example Solicitors LLP",
    relationship: "Estate solicitor",
    email: null,
    phone: null,
    address: null,
    references: [],
    holds_or_handles: null,
    notify_required: true,
    notification_status: "notified",
    notified_date: "2026-06-20",
    notified_method: "letter",
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
      const path = new URL(String(input)).pathname
      const method = init?.method ?? "GET"
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ method, path, body })
      const handler = routes[`${method} ${path}`] ?? routes[path]
      return handler ? handler(body) : json({ detail: "Not found" }, 404)
    }),
  )
  return calls
}

const defaultRoutes = {
  "/me": () => json({ email: "executor@example.com", role: "executor" }),
  "/estate": () => json({ id: "e1", name: "Example Estate" }),
  "/contacts": () => json(contacts),
  "/contacts/c1/interactions": () => json([]),
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
  return render(<ContactsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ContactsPage", () => {
  it("renders the contacts list with notification columns", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(await screen.findByText("Example Bank")).toBeInTheDocument()
    expect(screen.getByText("Example Solicitors")).toBeInTheDocument()
    expect(screen.getByText("Bank")).toBeInTheDocument()
    expect(screen.getByText("Pending")).toBeInTheDocument()
    expect(screen.getByText("Notified")).toBeInTheDocument()
    expect(screen.getByText("20 Jun 2026")).toBeInTheDocument()
  })

  it("filters to contacts still needing notification with the To notify preset", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText("Example Solicitors")).toBeInTheDocument()
    await user.click(screen.getByRole("button", { name: "To notify" }))

    expect(screen.getByText("Example Bank")).toBeInTheDocument()
    expect(screen.queryByText("Example Solicitors")).not.toBeInTheDocument()
  })

  it("creates a contact with the ContactCreate payload", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /contacts": (body) =>
        json({ ...contacts[0], ...(body as object), id: "c9" }, 201),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add contact" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.type(within(dialog).getByLabelText("Name"), "Example Utility")
    await user.selectOptions(
      within(dialog).getByLabelText("Category"),
      "utility",
    )
    await user.type(
      within(dialog).getByLabelText(/References/),
      "ACC-1, ACC-2",
    )
    await user.click(
      within(dialog).getByLabelText(/Notification required/),
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Add contact" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) => call.method === "POST" && call.path === "/contacts",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/contacts",
    )
    expect(post?.body).toEqual({
      estate_id: "e1",
      name: "Example Utility",
      category: "utility",
      org: null,
      relationship: null,
      email: null,
      phone: null,
      address: null,
      references: ["ACC-1", "ACC-2"],
      holds_or_handles: null,
      notify_required: true,
    })
  })

  it("marks a contact as notified via the quick action", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "PATCH /contacts/c1": (body) =>
        json({ ...contacts[0], ...(body as object) }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("Example Bank"))
    const detail = await screen.findByRole("dialog")
    await user.click(
      within(detail).getByRole("button", { name: "Mark notified" }),
    )

    const markDialog = await screen.findByRole("dialog", {
      name: /Mark Example Bank as notified/,
    })
    await user.selectOptions(
      within(markDialog).getByLabelText("Method"),
      "phone",
    )
    await user.click(
      within(markDialog).getByRole("button", { name: "Save notification" }),
    )

    const today = new Date().toISOString().slice(0, 10)
    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "PATCH" && call.path === "/contacts/c1",
        ),
      ).toBe(true)
    })
    const patch = calls.find(
      (call) => call.method === "PATCH" && call.path === "/contacts/c1",
    )
    expect(patch?.body).toEqual({
      notification_status: "notified",
      notified_date: today,
      notified_method: "phone",
    })
  })

  it("shows the interactions timeline newest first in the detail dialog", async () => {
    mockApi({
      ...defaultRoutes,
      "/contacts/c1/interactions": () =>
        json([
          {
            ...baseRow,
            id: "i1",
            contact_id: "c1",
            date: "2026-06-01",
            channel: "phone",
            direction: "outbound",
            summary: "Called the bereavement team.",
            follow_up_date: null,
            by_user: "executor@example.com",
            executor_private: false,
          },
          {
            ...baseRow,
            id: "i2",
            contact_id: "c1",
            date: "2026-06-15",
            channel: "letter",
            direction: "outbound",
            summary: "Posted the death certificate.",
            follow_up_date: null,
            by_user: "executor@example.com",
            executor_private: false,
          },
        ]),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("Example Bank"))
    const timeline = await screen.findByRole("list")
    const items = within(timeline).getAllByRole("listitem")
    expect(items[0]).toHaveTextContent("Posted the death certificate.")
    expect(items[1]).toHaveTextContent("Called the bereavement team.")
  })
})
