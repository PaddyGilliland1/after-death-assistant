/*
  Drafts module tests over a mocked fetch, against the landed backend
  contract: GET /agents/drafts lists PendingDraftOut rows, the draft
  content loads from GET /documents/{draft_id}/download as
  {draft_kind, payload}, and POST /agents/drafts/{approval_id}/approve
  takes {accepted?} for task suggestions. Covered: the list, the form
  draft detail with its gaps, the deliberate approve flow, the partial
  acceptance of task suggestions, the letter text, the 503 "not
  configured" state and the viewer's read-only page. Fixtures use
  synthetic example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { PendingDraft } from "./draft-meta"
import DraftsPage from "./index"

const pendingDrafts: PendingDraft[] = [
  {
    approval_id: "ap1",
    entity_ref: "document:df1",
    draft_kind: "iht400_draft",
    draft_id: "df1",
    title: "IHT400 pack draft",
    created_at: "2026-07-01T10:00:00Z",
    created_by: "executor@example.com",
  },
  {
    approval_id: "ap2",
    entity_ref: "document:dl1",
    draft_kind: "notification_letter",
    draft_id: "dl1",
    title: "Notification letter to Example Bank (draft)",
    created_at: "2026-07-02T09:00:00Z",
    created_by: "executor@example.com",
  },
  {
    approval_id: "ap3",
    entity_ref: "document:dt1",
    draft_kind: "task_suggestions",
    draft_id: "dt1",
    title: "Suggested tasks (draft)",
    created_at: "2026-04-14T09:00:00Z",
    created_by: "executor@example.com",
  },
]

/* Stored draft files: {draft_kind, payload}, as tools.store_draft_document writes them. */
const formFile = {
  draft_kind: "iht400_draft",
  payload: {
    forms: [
      {
        form: "IHT400",
        title: "Inheritance Tax account",
        sections: [
          {
            field_ref: "IHT400.gross_value",
            label: "Gross estate value",
            value: "512000.00",
            source_entity: "assessment:a1",
          },
          {
            field_ref: "IHT400.net_value",
            label: "Net estate value",
            value: "498000.00",
            source_entity: "assessment:a1",
          },
        ],
        gaps: [
          {
            item: "Example bank account value is an estimate",
            action: "Confirm the balance at the date of death with the bank",
          },
        ],
      },
    ],
    narrative: null,
    constants_version: "2026-04",
  },
}

const letterFile = {
  draft_kind: "notification_letter",
  payload: {
    letter_text:
      "DRAFT for executor review.\n\nDear Example Bank,\n\nWe write to notify you of the death of the account holder.",
    contact_id: "c1",
    purpose: "account closure",
    references: ["REF-0001"],
  },
}

const tasksFile = {
  draft_kind: "task_suggestions",
  payload: {
    suggestions: [
      { title: "Obtain a property valuation", description: "", priority: "high" },
      { title: "Notify the council", description: "Council tax account" },
    ],
  },
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
  "/agents/drafts": () => json(pendingDrafts),
  "/documents/df1/download": () => json(formFile),
  "/documents/dl1/download": () => json(letterFile),
  "/documents/dt1/download": () => json(tasksFile),
  "/contacts": () => json([]),
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
  return render(<DraftsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("DraftsPage", () => {
  it("lists pending drafts with kind, created date and creator", async () => {
    mockApi(defaultRoutes)
    renderPage()

    await screen.findByText("IHT400 pack draft")
    const table = screen.getByRole("table", { name: "Pending drafts" })
    expect(within(table).getByText("Form")).toBeInTheDocument()
    expect(within(table).getByText("Letter")).toBeInTheDocument()
    expect(within(table).getByText("Tasks")).toBeInTheDocument()
    expect(
      within(table).getByText("Notification letter to Example Bank (draft)"),
    ).toBeInTheDocument()
    expect(
      within(table).getByText("Suggested tasks (draft)"),
    ).toBeInTheDocument()
    expect(within(table).getByText("1 Jul 2026")).toBeInTheDocument()
    expect(
      within(table).getAllByText("executor@example.com").length,
    ).toBeGreaterThan(0)
  })

  it("shows a form draft as a field table with the gaps list", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("IHT400 pack draft"))
    const dialog = await screen.findByRole("dialog")

    expect(
      await within(dialog).findByText(
        "Gaps to resolve before this form is ready",
      ),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(
        "Example bank account value is an estimate. Confirm the balance at the date of death with the bank",
      ),
    ).toBeInTheDocument()

    const table = within(dialog).getByRole("table", { name: "IHT400 fields" })
    expect(within(table).getByText("Gross estate value")).toBeInTheDocument()
    expect(within(table).getByText("IHT400.gross_value")).toBeInTheDocument()
    expect(within(table).getByText("512000.00")).toBeInTheDocument()
    expect(within(dialog).getByText("Awaiting approval")).toBeInTheDocument()
  })

  it("approves a draft through the deliberate confirm step", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /agents/drafts/ap1/approve": () =>
        json({
          approval_id: "ap1",
          entity_ref: "document:df1",
          draft_kind: "iht400_draft",
          approved_by: "executor@example.com",
          approved_at: "2026-07-06T12:00:00Z",
          created_task_ids: [],
        }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("IHT400 pack draft"))
    await user.click(
      await screen.findByRole("button", { name: "Approve draft" }),
    )

    const confirm = await screen.findByRole("dialog", {
      name: "Approve this draft?",
    })
    expect(
      within(confirm).getByText(
        /Approval records your decision\. Nothing is sent or filed by this application; you remain responsible for submitting documents to HMRC or sending letters yourself\./,
      ),
    ).toBeInTheDocument()

    await user.click(within(confirm).getByRole("button", { name: "Approve" }))

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === "/agents/drafts/ap1/approve",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) =>
        call.method === "POST" && call.path === "/agents/drafts/ap1/approve",
    )
    expect(post?.body).toEqual({})
  })

  it("approves only the ticked task suggestions", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /agents/drafts/ap3/approve": () =>
        json({
          approval_id: "ap3",
          entity_ref: "document:dt1",
          draft_kind: "task_suggestions",
          approved_by: "executor@example.com",
          approved_at: "2026-07-06T12:00:00Z",
          created_task_ids: ["t9"],
        }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("Suggested tasks (draft)"))
    const dialog = await screen.findByRole("dialog")
    const list = await within(dialog).findByRole("list", {
      name: "Suggested tasks",
    })
    const boxes = within(list).getAllByRole("checkbox")
    expect(boxes).toHaveLength(2)
    expect(boxes[0]).toBeChecked()

    await user.click(boxes[1])
    await user.click(
      within(dialog).getByRole("button", { name: "Approve draft" }),
    )

    const confirm = await screen.findByRole("dialog", {
      name: "Approve this draft?",
    })
    expect(
      within(confirm).getByText(
        /1 of 2 suggestions will be created as tasks\./,
      ),
    ).toBeInTheDocument()
    await user.click(within(confirm).getByRole("button", { name: "Approve" }))

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === "/agents/drafts/ap3/approve",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) =>
        call.method === "POST" && call.path === "/agents/drafts/ap3/approve",
    )
    expect(post?.body).toEqual({ accepted: [0] })
  })

  it("renders a letter draft as formatted text with its references", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByText("Notification letter to Example Bank (draft)"),
    )
    const dialog = await screen.findByRole("dialog")
    expect(
      await within(dialog).findByText(/Dear Example Bank,/),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(/References quoted: REF-0001/),
    ).toBeInTheDocument()
  })

  it("renders the calm line when the letter agent returns 503", async () => {
    mockApi({
      ...defaultRoutes,
      "/contacts": () =>
        json([
          {
            id: "c1",
            name: "Example Bank",
            org: null,
            category: "bank",
          },
        ]),
      "POST /agents/draft-letter": () =>
        json({ detail: "ANTHROPIC_API_KEY is not configured" }, 503),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Draft letter" }),
    )
    const dialog = await screen.findByRole("dialog")
    await user.selectOptions(
      within(dialog).getByLabelText("Contact"),
      "c1",
    )
    await user.type(
      within(dialog).getByLabelText("Purpose"),
      "notify of the death",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Draft letter" }),
    )

    expect(
      await within(dialog).findByText(
        "The drafting assistant is not configured yet.",
      ),
    ).toBeInTheDocument()
  })

  it("gives a viewer a calm explanation and never calls the agents API", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderPage()

    expect(
      await screen.findByText(
        "Agent drafts are visible to executors and admins only. Approved letters and forms appear in the documents vault.",
      ),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Draft IHT400" }),
    ).not.toBeInTheDocument()
    expect(
      calls.some((call) => call.path.startsWith("/agents/drafts")),
    ).toBe(false)
  })
})
