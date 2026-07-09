/*
  Admin tests over a mocked fetch: the activity feed, the audit denial
  state for viewers, and the search section with grouped, typed results
  linking to the owning modules.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import AdminPage from "./index"

const activity = [
  {
    id: "ev1",
    actor: "executor@example.com",
    action: "create",
    entity: "document:doc1",
    timestamp: "2026-07-01T10:00:00Z",
  },
  {
    id: "ev2",
    actor: "admin@example.com",
    action: "update",
    entity: "asset:a1",
    timestamp: "2026-07-02T11:00:00Z",
  },
]

const searchHits = [
  { type: "contact", id: "c1", label: "Example Bank plc" },
  { type: "document", id: "doc2", label: "Bank statement March" },
  { type: "asset", id: "a1", label: "Current account at Example Bank" },
]

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type Handler = (init?: RequestInit) => Response

function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const method = (init?.method ?? "GET").toUpperCase()
      const handler = routes[`${method} ${url.pathname}`] ?? routes[url.pathname]
      return handler ? handler(init) : json({ detail: "Not found" }, 404)
    },
  )
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

function renderAdmin() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    )
  }
  return render(<AdminPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AdminPage", () => {
  it("shows the activity feed by default", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/activity": () => json(activity),
    })
    renderAdmin()

    expect(
      await screen.findByText("executor@example.com"),
    ).toBeInTheDocument()
    expect(screen.getByText("admin@example.com")).toBeInTheDocument()
    expect(screen.getByText("Document")).toBeInTheDocument()
    expect(screen.getByText("Asset")).toBeInTheDocument()
  })

  it("groups search results by type with links to the owning module", async () => {
    const user = userEvent.setup()
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/activity": () => json(activity),
      "/search": () => json(searchHits),
    })
    renderAdmin()

    await user.click(screen.getByRole("button", { name: "Search" }))
    await user.type(
      screen.getByLabelText("Search the estate's records"),
      "bank",
    )
    await user.click(screen.getByRole("button", { name: "Run search" }))

    expect(await screen.findByText("Example Bank plc")).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Contacts" }),
    ).toBeInTheDocument()
    expect(screen.getByRole("heading", { name: "Assets" })).toBeInTheDocument()
    expect(
      screen.getByRole("heading", { name: "Documents" }),
    ).toBeInTheDocument()

    const contactLink = screen
      .getByText("Example Bank plc")
      .closest("a") as HTMLAnchorElement
    expect(contactLink).toHaveAttribute("href", "/contacts")
    const documentLink = screen
      .getByText("Bank statement March")
      .closest("a") as HTMLAnchorElement
    expect(documentLink).toHaveAttribute("href", "/documents")
  })

  it("shows a polite denial when the audit trail returns 403", async () => {
    const user = userEvent.setup()
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
      "/activity": () => json(activity),
      "/audit": () =>
        json({ detail: "This action needs the executor or admin role." }, 403),
    })
    renderAdmin()

    await user.click(await screen.findByRole("button", { name: "Audit" }))

    expect(
      await screen.findByText(
        /only available to executors and administrators/,
      ),
    ).toBeInTheDocument()
  })
})
