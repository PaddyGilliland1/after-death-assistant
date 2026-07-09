/*
  Notification bell tests: the unread count in the button label and
  badge, the dropdown list, mark-read on click and mark all read, plus
  the viewer's read-only list.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AppLayout } from "./app-layout"

const notifications = [
  {
    id: "n1",
    event_type: "cost_recorded",
    entity_ref: "cost:c1",
    message: "A cost of £120 was recorded.",
    read_at: null,
    created_at: "2026-07-01T10:00:00Z",
  },
  {
    id: "n2",
    event_type: "task_completed",
    entity_ref: "task:t1",
    message: "A task was completed.",
    read_at: null,
    created_at: "2026-07-02T09:00:00Z",
  },
  {
    id: "n3",
    event_type: "asset_added",
    entity_ref: "asset:a1",
    message: "An asset was added earlier.",
    read_at: "2026-04-14T09:00:00Z",
    created_at: "2026-06-30T09:00:00Z",
  },
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

function renderLayout() {
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
  return render(
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<div>Home content</div>} />
      </Route>
    </Routes>,
    { wrapper: Wrapper },
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AppLayout notification bell", () => {
  it("shows the unread count in the accessible label and badge", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/notifications": () => json(notifications),
    })
    renderLayout()

    const bell = await screen.findByRole("button", {
      name: "Notifications (2 unread)",
    })
    expect(bell).toBeInTheDocument()
    expect(bell).toHaveAttribute("aria-expanded", "false")
  })

  it("opens the list and marks a notification read on click", async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/notifications": () => json(notifications),
      "POST /notifications/n1/read": () =>
        json({ ...notifications[0], read_at: "2026-07-06T12:00:00Z" }),
    })
    renderLayout()

    await user.click(
      await screen.findByRole("button", { name: "Notifications (2 unread)" }),
    )
    expect(
      screen.getByText("A cost of £120 was recorded."),
    ).toBeInTheDocument()
    expect(screen.getByText("An asset was added earlier.")).toBeInTheDocument()

    await user.click(
      screen.getByRole("button", { name: /A cost of £120 was recorded/ }),
    )

    await waitFor(() => {
      const readCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          init?.method === "POST" &&
          new URL(String(input)).pathname === "/notifications/n1/read",
      )
      expect(readCall).toBeTruthy()
    })
  })

  it("marks everything read with the mark all action", async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/notifications": () => json(notifications),
      "POST /notifications/read-all": () => json({ marked_read: 2 }),
    })
    renderLayout()

    await user.click(
      await screen.findByRole("button", { name: "Notifications (2 unread)" }),
    )
    await user.click(screen.getByRole("button", { name: "Mark all read" }))

    await waitFor(() => {
      const readAllCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          init?.method === "POST" &&
          new URL(String(input)).pathname === "/notifications/read-all",
      )
      expect(readAllCall).toBeTruthy()
    })
  })

  it("gives a viewer the list without mark-read affordances", async () => {
    const user = userEvent.setup()
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
      "/notifications": () => json(notifications),
    })
    renderLayout()

    await user.click(
      await screen.findByRole("button", { name: "Notifications (2 unread)" }),
    )

    expect(
      screen.getByText("A cost of £120 was recorded."),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Mark all read" }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /A cost of £120 was recorded/ }),
    ).not.toBeInTheDocument()
  })
})
