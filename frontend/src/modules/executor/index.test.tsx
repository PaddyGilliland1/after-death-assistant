/*
  Decision log tests over a mocked fetch: the list renders with the
  immutability copy and no edit or delete affordances, the create form
  posts the full payload (repeatable options, agreed-by emails), and the
  detail dialog shows the full rationale.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import ExecutorPage from "./index"

// Synthetic emails and titles only; no personal data in fixtures.
const decisions = [
  {
    id: "d1",
    estate_id: "e1",
    created_at: "2026-06-01T10:00:00Z",
    updated_at: "2026-06-01T10:00:00Z",
    created_by: "executor.one@example.com",
    date: "2026-06-01",
    title: "Instruct a valuer for the property",
    rationale: "Three quotes were compared; this firm is RICS registered.",
    options_considered: [
      { option: "Instruct firm A" },
      { option: "Instruct firm B", notes: "Cheaper but slower" },
    ],
    agreed_by: ["executor.two@example.com"],
    made_by: "executor.one@example.com",
    executor_private: false,
  },
]

const estate = { id: "e1", name: "Estate under administration" }
const me = { email: "executor.one@example.com", role: "executor" }

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type RouteHandler = (init?: RequestInit) => Response

/** Routes keyed by "METHOD /path"; a bare "/path" matches any method. */
function mockApi(routes: Record<string, RouteHandler>) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname
      const method = init?.method ?? "GET"
      const handler = routes[`${method} ${path}`] ?? routes[path]
      return handler ? handler(init) : json({ detail: "Not found" }, 404)
    },
  )
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
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
  return render(<ExecutorPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("ExecutorPage (decision log)", () => {
  it("lists decisions with the immutability copy and no edit or delete affordances", async () => {
    mockApi({
      "/me": () => json(me),
      "/estate": () => json(estate),
      "GET /decisions": () => json(decisions),
    })
    renderPage()

    expect(
      await screen.findByText("Instruct a valuer for the property"),
    ).toBeInTheDocument()
    expect(screen.getAllByText("executor.one@example.com").length).toBe(1)

    expect(screen.getByRole("note")).toHaveTextContent(
      "once recorded they cannot be changed or deleted",
    )

    expect(
      screen.queryByRole("button", { name: /edit|delete|archive/i }),
    ).not.toBeInTheDocument()
  })

  it("shows the full rationale in the detail dialog", async () => {
    mockApi({
      "/me": () => json(me),
      "/estate": () => json(estate),
      "GET /decisions": () => json(decisions),
    })
    renderPage()
    const user = userEvent.setup({ pointerEventsCheck: 0 })

    await user.click(
      await screen.findByText("Instruct a valuer for the property"),
    )

    const dialog = await screen.findByRole("dialog")
    expect(
      within(dialog).getByText(
        "Three quotes were compared; this firm is RICS registered.",
      ),
    ).toBeInTheDocument()
    expect(within(dialog).getByText(/Instruct firm A/)).toBeInTheDocument()
    expect(
      within(dialog).getByText(/Instruct firm B \(Cheaper but slower\)/),
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText(/This record cannot be changed\./),
    ).toBeInTheDocument()
  })

  it("records a decision with options and agreed-by emails", async () => {
    const fetchMock = mockApi({
      "/me": () => json(me),
      "/estate": () => json(estate),
      "GET /decisions": () => json([]),
      "POST /decisions": () =>
        json({ ...decisions[0], id: "d2", title: "Sell the listed shares" }, 201),
    })
    renderPage()
    const user = userEvent.setup({ pointerEventsCheck: 0 })

    await user.click(
      await screen.findByRole("button", { name: /record decision/i }),
    )
    const dialog = await screen.findByRole("dialog", {
      name: /record a decision/i,
    })

    await user.type(
      within(dialog).getByLabelText(/^title$/i),
      "Sell the listed shares",
    )
    await user.type(
      within(dialog).getByLabelText(/date decided/i),
      "2026-07-01",
    )
    await user.type(
      within(dialog).getByLabelText(/rationale/i),
      "Best available price this quarter.",
    )
    await user.type(within(dialog).getByLabelText("Option 1"), "Sell now")
    await user.click(
      within(dialog).getByRole("button", { name: /add another option/i }),
    )
    await user.type(
      within(dialog).getByLabelText("Option 2"),
      "Hold for six months",
    )
    await user.type(
      within(dialog).getByLabelText(/agreed by/i),
      "executor.two@example.com, executor.three@example.com",
    )
    await user.click(
      within(dialog).getByRole("button", { name: /record this decision/i }),
    )

    await waitFor(() => {
      const call = fetchMock.mock.calls.find(
        ([input, init]) =>
          init?.method === "POST" &&
          new URL(String(input)).pathname === "/decisions",
      )
      expect(call).toBeDefined()
      const body = JSON.parse(String(call?.[1]?.body)) as Record<
        string,
        unknown
      >
      expect(body.estate_id).toBe("e1")
      expect(body.title).toBe("Sell the listed shares")
      expect(body.date).toBe("2026-07-01")
      expect(body.rationale).toBe("Best available price this quarter.")
      expect(body.options_considered).toEqual([
        { option: "Sell now" },
        { option: "Hold for six months" },
      ])
      expect(body.agreed_by).toEqual([
        "executor.two@example.com",
        "executor.three@example.com",
      ])
    })
  })

  it("hides the record action from viewers", async () => {
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
      "/estate": () => json(estate),
      "GET /decisions": () => json(decisions),
    })
    renderPage()

    expect(
      await screen.findByText("Instruct a valuer for the property"),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /record decision/i }),
    ).not.toBeInTheDocument()
  })
})
