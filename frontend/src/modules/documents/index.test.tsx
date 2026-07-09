/*
  Documents tests over a mocked fetch: the vault list, the multipart
  upload (FormData fields as the backend's Form(...) parameters expect
  them), the empty state and the viewer's read-only page.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import DocumentsPage from "./index"

const documents = [
  {
    id: "doc1",
    title: "Sealed grant copy",
    type: "grant_of_probate",
    mime: "application/pdf",
    version: 2,
    access_roles: ["executor", "admin"],
    executor_private: true,
    links: [],
    created_at: "2026-06-20T10:00:00Z",
    created_by: "executor@example.com",
  },
  {
    id: "doc2",
    title: "Bank statement March",
    type: "bank_statement",
    mime: "application/pdf",
    version: 1,
    access_roles: [],
    executor_private: false,
    links: [],
    created_at: "2026-06-22T10:00:00Z",
    created_by: "executor@example.com",
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

function renderDocuments() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
  return render(<DocumentsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("DocumentsPage", () => {
  it("lists documents with type, version, date, access and private badge", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/documents": () => json(documents),
    })
    renderDocuments()

    expect(await screen.findByText("Sealed grant copy")).toBeInTheDocument()
    expect(screen.getByText("Grant of probate")).toBeInTheDocument()
    expect(screen.getByText("Bank statement March")).toBeInTheDocument()
    expect(screen.getByText("Bank statement")).toBeInTheDocument()
    expect(screen.getByText("2")).toBeInTheDocument()
    expect(screen.getByText("20 Jun 2026")).toBeInTheDocument()
    expect(screen.getByText("Executor, Admin")).toBeInTheDocument()
    expect(screen.getByText("All roles")).toBeInTheDocument()
    expect(
      screen.getByText("Private", { selector: "[data-slot=badge]" }),
    ).toBeInTheDocument()
  })

  it("uploads a document as multipart FormData with all the fields", async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/documents": () => json(documents),
      "POST /documents": () => json(documents[0], 201),
    })
    renderDocuments()

    await user.click(
      await screen.findByRole("button", { name: /Upload document/ }),
    )
    await user.type(screen.getByLabelText("Title"), "Grant of probate")
    await user.selectOptions(screen.getByLabelText("Type"), "grant_of_probate")
    await user.upload(
      screen.getByLabelText("File"),
      new File(["contents"], "grant.pdf", { type: "application/pdf" }),
    )
    await user.click(screen.getByLabelText("Executor"))
    await user.click(screen.getByLabelText("Admin"))
    await user.click(
      screen.getByLabelText("Executor private (never shown to viewers)"),
    )
    await user.click(screen.getByRole("button", { name: "Upload" }))

    await waitFor(() => {
      const uploadCall = fetchMock.mock.calls.find(
        ([input, init]) =>
          init?.method === "POST" &&
          new URL(String(input)).pathname === "/documents",
      )
      expect(uploadCall).toBeTruthy()
      const body = uploadCall?.[1]?.body as FormData
      expect(body).toBeInstanceOf(FormData)
      expect(body.get("title")).toBe("Grant of probate")
      expect(body.get("type")).toBe("grant_of_probate")
      expect(body.get("access_roles")).toBe("executor,admin")
      expect(body.get("executor_private")).toBe("true")
      const file = body.get("file") as File
      expect(file.name).toBe("grant.pdf")
    })
  })

  it("explains the vault in the empty state", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "/documents": () => json([]),
    })
    renderDocuments()

    expect(
      await screen.findByText("The document vault is empty."),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/keeps the estate's paperwork safe/),
    ).toBeInTheDocument()
  })

  it("hides the upload action from a viewer", async () => {
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
      "/documents": () => json(documents),
    })
    renderDocuments()

    expect(await screen.findByText("Sealed grant copy")).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /Upload document/ }),
    ).not.toBeInTheDocument()
  })
})
