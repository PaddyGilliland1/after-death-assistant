/*
  Timeline tests over a mocked fetch: steps from /process/timeline with
  their derived statuses, the deadlines panel with overdue flags and
  citations, the write-gated status select and recompute action, and the
  viewer's read-only view.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import TimelinePage from "./index"

const timeline = [
  {
    step_id: "s1",
    order: 1,
    name: "Register the death",
    stored_status: "done",
    derived_status: "done",
    deadline_type: null,
    deadline_date: null,
  },
  {
    step_id: "s2",
    order: 2,
    name: "Value the estate",
    stored_status: "in_progress",
    derived_status: "current",
    deadline_type: "iht_payment",
    deadline_date: "2099-12-31",
  },
  {
    step_id: "s3",
    order: 3,
    name: "Apply for the grant",
    stored_status: null,
    derived_status: "upcoming",
    deadline_type: null,
    deadline_date: null,
  },
]

const deadlines = [
  {
    id: "d1",
    type: "iht_payment",
    derived_date: "2099-12-31",
    reminders: [
      {
        kind: "citation",
        basis: "IHTA 1984 s.226",
        derived_by: "app.domain.deadlines",
        domain_name: "IHT payment due",
      },
    ],
  },
  {
    id: "d2",
    type: "s27_claim",
    derived_date: "2020-01-31",
    reminders: [],
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

function renderTimeline() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
  return render(<TimelinePage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("TimelinePage", () => {
  it("renders every step with its derived status", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/process/timeline": () => json(timeline),
      "/deadlines": () => json(deadlines),
    })
    renderTimeline()

    expect(await screen.findByText("Register the death")).toBeInTheDocument()
    expect(screen.getByText("Value the estate")).toBeInTheDocument()
    expect(screen.getByText("Apply for the grant")).toBeInTheDocument()
    const badge = { selector: "[data-slot=badge]" }
    expect(screen.getByText("Done", badge)).toBeInTheDocument()
    expect(screen.getByText("Current", badge)).toBeInTheDocument()
    expect(screen.getByText("Upcoming", badge)).toBeInTheDocument()
  })

  it("shows the linked deadline date and citation on a step", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/process/timeline": () => json(timeline),
      "/deadlines": () => json(deadlines),
    })
    renderTimeline()

    expect(
      await screen.findByText(/Iht payment deadline: 31 Dec 2099/),
    ).toBeInTheDocument()
    expect(
      (await screen.findAllByText(/IHTA 1984 s\.226/)).length,
    ).toBeGreaterThan(0)
  })

  it("lists deadlines in the panel with an overdue badge", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/process/timeline": () => json(timeline),
      "/deadlines": () => json(deadlines),
    })
    renderTimeline()

    expect(await screen.findByText("S27 claim")).toBeInTheDocument()
    expect(screen.getByText("Iht payment")).toBeInTheDocument()
    expect(screen.getByText("31 Jan 2020")).toBeInTheDocument()
    expect(screen.getByText("Overdue")).toBeInTheDocument()
  })

  it("lets a writer change a step's status with PATCH", async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/process/timeline": () => json(timeline),
      "/deadlines": () => json(deadlines),
      "PATCH /process/steps/s2": () =>
        json({
          id: "s2",
          order: 2,
          name: "Value the estate",
          status: "done",
          deadline_id: null,
        }),
    })
    renderTimeline()

    const select = await screen.findByLabelText("Status for Value the estate")
    await user.selectOptions(select, "done")

    await waitFor(() => {
      const patchCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          init?.method === "PATCH" &&
          new URL(String(input)).pathname === "/process/steps/s2",
      )
      expect(patchCall).toBeTruthy()
      expect(JSON.parse(String(patchCall?.[1]?.body))).toEqual({
        status: "done",
      })
    })
  })

  it("recomputes deadlines and reports the result", async () => {
    const user = userEvent.setup()
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/process/timeline": () => json(timeline),
      "/deadlines": () => json(deadlines),
      "POST /deadlines/recompute": () =>
        json({ created: 2, updated: 1, deadlines: [] }),
    })
    renderTimeline()

    await user.click(
      await screen.findByRole("button", { name: /Recompute deadlines/ }),
    )

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Deadlines recomputed: 2 added, 1 updated.",
    )
  })

  it("hides write affordances from a viewer", async () => {
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
      "/process/timeline": () => json(timeline),
      "/deadlines": () => json(deadlines),
    })
    renderTimeline()

    expect(await screen.findByText("Register the death")).toBeInTheDocument()
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /Recompute deadlines/ }),
    ).not.toBeInTheDocument()
  })
})
