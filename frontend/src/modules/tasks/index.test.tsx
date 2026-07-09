/*
  Tasks module tests over a mocked fetch: the list renders with the
  blocked indicator, creating posts the TaskCreate payload (assignees as
  an array, checklist of {text, done}), and the backend's 409 blocking
  message is surfaced when a blocked task is moved to done. Fixtures use
  example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import type { Task } from "@/lib/types"

import TasksPage from "./index"

const baseRow = {
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
  created_by: "executor@example.com",
  archived_at: null,
  archive_reason: null,
}

const tasks: Task[] = [
  {
    ...baseRow,
    id: "t1",
    title: "Apply for probate",
    description: "Submit the PA1P application.",
    assignees: ["executor@example.com"],
    status: "in_progress",
    priority: "high",
    start_date: "2026-06-01",
    due_date: "2026-08-01",
    blocked_by: ["t2"],
    blocks: [],
    checklist: [{ text: "Gather valuations", done: true }],
    process_step_id: null,
    source: null,
    reminder: null,
    executor_private: false,
  },
  {
    ...baseRow,
    id: "t2",
    title: "Value the estate",
    description: null,
    assignees: [],
    status: "todo",
    priority: "medium",
    start_date: null,
    due_date: "2026-07-15",
    blocked_by: [],
    blocks: ["t1"],
    checklist: [],
    process_step_id: null,
    source: null,
    reminder: null,
    executor_private: false,
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
  "/tasks": () => json(tasks),
  "/tasks/t1/comments": () => json([]),
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
  return render(<TasksPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("TasksPage", () => {
  it("renders the tasks list with the blocked indicator", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(await screen.findByText("Apply for probate")).toBeInTheDocument()
    const table = screen.getByRole("table", { name: "Tasks" })
    expect(within(table).getByText("Value the estate")).toBeInTheDocument()
    expect(within(table).getByText("In progress")).toBeInTheDocument()
    expect(within(table).getByText("1 Aug 2026")).toBeInTheDocument()

    // The blocked badge sits in the row of the task with dependencies.
    const blockedRow = within(table)
      .getByText("Apply for probate")
      .closest("tr") as HTMLElement
    expect(within(blockedRow).getByText("Blocked")).toBeInTheDocument()
    const openRow = within(table)
      .getByText("Value the estate")
      .closest("tr") as HTMLElement
    expect(within(openRow).queryByText("Blocked")).not.toBeInTheDocument()
  })

  it("creates a task with assignees as an array and a checklist", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /tasks": (body) =>
        json({ ...tasks[1], ...(body as object), id: "t9" }, 201),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("button", { name: "Add task" }))
    const dialog = await screen.findByRole("dialog")
    await user.type(
      within(dialog).getByLabelText("Title"),
      "Notify the council",
    )
    await user.type(
      within(dialog).getByLabelText(/Assignees/),
      "one@example.com, two@example.com",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Add checklist item" }),
    )
    await user.type(
      within(dialog).getByLabelText("Checklist item 1"),
      "Find the council tax reference",
    )
    await user.click(
      within(dialog).getByLabelText("Value the estate"),
    )
    await user.click(within(dialog).getByRole("button", { name: "Add task" }))

    await waitFor(() => {
      expect(
        calls.some((call) => call.method === "POST" && call.path === "/tasks"),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/tasks",
    )
    expect(post?.body).toEqual({
      estate_id: "e1",
      status: "todo",
      title: "Notify the council",
      description: null,
      priority: null,
      start_date: null,
      due_date: null,
      assignees: ["one@example.com", "two@example.com"],
      blocked_by: ["t2"],
      checklist: [{ text: "Find the council tax reference", done: false }],
      executor_private: false,
    })
  })

  it("surfaces the backend 409 blocking message when completing a blocked task", async () => {
    mockApi({
      ...defaultRoutes,
      "PATCH /tasks/t1": () =>
        json(
          {
            detail: {
              message:
                "This task cannot move to done while it is blocked by open tasks.",
              blocking: ["t2"],
            },
          },
          409,
        ),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByText("Apply for probate"))
    const dialog = await screen.findByRole("dialog")
    await user.selectOptions(within(dialog).getByLabelText("Status"), "done")

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent(
      "This task cannot move to done while it is blocked by open tasks.",
    )
    expect(alert).toHaveTextContent("Value the estate")
  })

  it("filters tasks by status and due-before date", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderPage()

    expect(await screen.findByText("Apply for probate")).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText("Status"), "todo")
    expect(screen.queryByText("Apply for probate")).not.toBeInTheDocument()
    expect(screen.getByText("Value the estate")).toBeInTheDocument()

    await user.selectOptions(screen.getByLabelText("Status"), "")
    // Due before 20 Jul 2026: only the task due 15 Jul remains.
    const dueBefore = screen.getByLabelText("Due before")
    await user.type(dueBefore, "2026-07-20")
    expect(screen.queryByText("Apply for probate")).not.toBeInTheDocument()
    expect(screen.getByText("Value the estate")).toBeInTheDocument()
  })
})
