/*
  Suggested next actions tests over a mocked fetch: the button posts to
  /agents/suggest-tasks, the returned suggestions render inline with the
  link to the drafts approval flow, a 503 renders the calm "not
  configured" line, and viewers see nothing. Fixtures use synthetic data
  only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { afterEach, describe, expect, it, vi } from "vitest"

import { SuggestActions } from "./suggest-actions"

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

interface RecordedCall {
  method: string
  path: string
}

function mockApi(routes: Record<string, () => Response>): RecordedCall[] {
  const calls: RecordedCall[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const method = init?.method ?? "GET"
      calls.push({ method, path: url.pathname })
      const handler =
        routes[`${method} ${url.pathname}`] ?? routes[url.pathname]
      return handler ? handler() : json({ detail: "Not found" }, 404)
    }),
  )
  return calls
}

function renderActions() {
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
  return render(<SuggestActions />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("SuggestActions", () => {
  it("posts to suggest-tasks and shows the suggestions with a drafts link", async () => {
    const calls = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "POST /agents/suggest-tasks": () =>
        json(
          {
            draft_id: "dt1",
            approval_id: "ap3",
            status: "pending_approval",
            suggestions: [
              { title: "Obtain a property valuation", description: "" },
              {
                title: "Notify the council",
                description: "Council tax account",
              },
            ],
          },
          201,
        ),
    })
    const user = userEvent.setup()
    renderActions()

    await user.click(
      await screen.findByRole("button", { name: "Suggest next actions" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" && call.path === "/agents/suggest-tasks",
        ),
      ).toBe(true)
    })

    const list = await screen.findByRole("list", { name: "Suggested tasks" })
    expect(screen.getByText("Obtain a property valuation")).toBeInTheDocument()
    expect(list).toBeInTheDocument()

    const link = screen.getByRole("link", { name: "Drafts page" })
    expect(link).toHaveAttribute("href", "/drafts")
  })

  it("renders the calm line when the assistant returns 503", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "POST /agents/suggest-tasks": () =>
        json({ detail: "Agent model is not configured" }, 503),
    })
    const user = userEvent.setup()
    renderActions()

    await user.click(
      await screen.findByRole("button", { name: "Suggest next actions" }),
    )
    expect(
      await screen.findByText("The drafting assistant is not configured yet."),
    ).toBeInTheDocument()
  })

  it("renders nothing for a viewer", async () => {
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderActions()

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Suggest next actions" }),
      ).not.toBeInTheDocument()
    })
  })
})
