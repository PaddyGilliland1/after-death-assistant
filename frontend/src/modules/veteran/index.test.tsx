/*
  Veteran checklist module tests over a mocked fetch: the checklist
  renders as a calm task list with statuses, and the "Add these to tasks"
  action posts to /veteran/seed-tasks and reports the result. Fixtures
  use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import VeteranPage from "./index"

const checklist = [
  {
    order: 1,
    title: "Notify Veterans UK of the death",
    description: "They administer war pensions and service pensions.",
    url: "https://example.com/veterans-uk",
    task_id: "t1",
    task_status: "done",
  },
  {
    order: 2,
    title: "Check for a service pension",
    description: "Armed forces pensions may include dependant benefits.",
    url: null,
    task_id: null,
    task_status: null,
  },
  {
    order: 3,
    title: "Contact SSAFA for support",
    description: "The armed forces charity can support the family.",
    url: null,
    task_id: "t3",
    task_status: "in_progress",
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
  "/veteran/checklist": () => json(checklist),
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
  return render(<VeteranPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("VeteranPage", () => {
  it("renders the checklist with item statuses and the support copy", async () => {
    mockApi(defaultRoutes)
    renderPage()

    const list = await screen.findByRole("list", { name: "Checklist items" })
    expect(
      within(list).getByText("Notify Veterans UK of the death"),
    ).toBeInTheDocument()
    expect(
      within(list).getByText(
        "They administer war pensions and service pensions.",
      ),
    ).toBeInTheDocument()
    expect(within(list).getByText("Done")).toBeInTheDocument()
    expect(within(list).getByText("Not started")).toBeInTheDocument()
    expect(within(list).getByText("In progress")).toBeInTheDocument()

    expect(
      screen.getByText(/support checklist for estates where the person/),
    ).toBeInTheDocument()
  })

  it("seeds tasks from the checklist and reports the result", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /veteran/seed-tasks": () =>
        json({
          created: [
            "Notify Veterans UK of the death",
            "Check for a service pension",
            "Contact SSAFA for support",
          ],
          skipped: [],
        }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(
      await screen.findByRole("button", { name: "Add these to tasks" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" && call.path === "/veteran/seed-tasks",
        ),
      ).toBe(true)
    })
    expect(
      await screen.findByText("3 tasks added to the task list."),
    ).toBeInTheDocument()
  })

  it("hides the seed action for viewers", async () => {
    mockApi({
      ...defaultRoutes,
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderPage()

    await screen.findByRole("list", { name: "Checklist items" })
    expect(
      screen.queryByRole("button", { name: "Add these to tasks" }),
    ).not.toBeInTheDocument()
  })
})
