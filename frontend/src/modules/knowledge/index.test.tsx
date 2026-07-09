/*
  Knowledge module tests over a mocked fetch: search renders hits with
  the form code badge and the OGL licence line, QA answers render with
  [n] citations linked to the sources list, a refusal renders calmly, a
  503 shows the not-configured message, and the guidance disclaimer is
  always visible. Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import KnowledgePage from "./index"

const searchHits = [
  {
    doc_id: "d1",
    doc_title: "IHT400 notes",
    form_code: "IHT400",
    source_url: "https://example.com/iht400-notes",
    licence: "OGL v3",
    fetch_date: "2026-06-01",
    chunk_text:
      "You must send form IHT400 when the estate is not an excepted estate.",
    chunk_index: 4,
    score: 0.92,
  },
]

const docs = [
  {
    id: "d1",
    title: "IHT400 notes",
    form_code: "IHT400",
    source_url: "https://example.com/iht400-notes",
    licence: "OGL v3",
    fetch_date: "2026-06-01",
  },
]

const qaAnswer = {
  answer:
    "Form IHT400 is needed when the estate is not an excepted estate [1].",
  sources: [
    {
      n: 1,
      doc_title: "IHT400 notes",
      source_url: "https://example.com/iht400-notes",
      form_code: "IHT400",
    },
  ],
  refused: false,
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
  "/knowledge/search": () => json(searchHits),
  "/knowledge/docs": () => json(docs),
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
  return render(<KnowledgePage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("KnowledgePage", () => {
  it("always shows the guidance disclaimer", async () => {
    mockApi(defaultRoutes)
    renderPage()

    expect(
      await screen.findByText(
        "Guidance only, not legal or tax advice. Answers cite the cached official sources.",
      ),
    ).toBeInTheDocument()
  })

  it("searches and renders hits with form code badge and OGL licence line", async () => {
    const calls = mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderPage()

    await user.type(
      await screen.findByLabelText("Search the library"),
      "IHT400",
    )
    await user.click(screen.getByRole("button", { name: "Search" }))

    const results = await screen.findByRole("list", {
      name: "Search results",
    })
    expect(within(results).getByText("IHT400 notes")).toBeInTheDocument()
    expect(within(results).getByText("IHT400")).toBeInTheDocument()
    expect(
      within(results).getByText(/You must send form IHT400/),
    ).toBeInTheDocument()
    expect(
      within(results).getByText(
        /Contains public sector information licensed under the Open Government Licence/,
      ),
    ).toBeInTheDocument()
    const link = within(results).getByRole("link", { name: /View source/ })
    expect(link).toHaveAttribute("rel", "noopener noreferrer")

    expect(
      calls.some(
        (call) =>
          call.method === "GET" &&
          call.path === "/knowledge/search?q=IHT400",
      ),
    ).toBe(true)
  })

  it("asks a question and renders the answer with linked citations", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      "POST /knowledge/qa": () => json(qaAnswer),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("tab", { name: "Ask" }))
    await user.type(
      screen.getByLabelText("Your question"),
      "When is IHT400 needed?",
    )
    await user.click(screen.getByRole("button", { name: "Ask" }))

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" && call.path === "/knowledge/qa",
        ),
      ).toBe(true)
    })
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/knowledge/qa",
    )
    expect(post?.body).toEqual({ question: "When is IHT400 needed?" })

    const citation = await screen.findByRole("link", {
      name: "Citation 1: IHT400 notes",
    })
    expect(citation.getAttribute("href")).toMatch(/-source-1$/)

    const sources = screen.getByRole("list", { name: "Sources" })
    expect(
      within(sources).getByRole("link", { name: /IHT400 notes/ }),
    ).toHaveAttribute("href", "https://example.com/iht400-notes")
  })

  it("shows a refusal calmly", async () => {
    mockApi({
      ...defaultRoutes,
      "POST /knowledge/qa": () =>
        json({
          answer: "The cached sources do not cover this question.",
          sources: [],
          refused: true,
        }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("tab", { name: "Ask" }))
    await user.type(screen.getByLabelText("Your question"), "Anything?")
    await user.click(screen.getByRole("button", { name: "Ask" }))

    expect(
      await screen.findByText("The assistant did not answer this one."),
    ).toBeInTheDocument()
    expect(
      screen.getByText("The cached sources do not cover this question."),
    ).toBeInTheDocument()
  })

  it("shows the not-configured message on a 503", async () => {
    mockApi({
      ...defaultRoutes,
      "POST /knowledge/qa": () =>
        json({ detail: "LLM backend not configured" }, 503),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("tab", { name: "Ask" }))
    await user.type(screen.getByLabelText("Your question"), "Anything?")
    await user.click(screen.getByRole("button", { name: "Ask" }))

    expect(
      await screen.findByText("The assistant is not configured yet."),
    ).toBeInTheDocument()
  })

  it("shows the ingest action to admins only", async () => {
    mockApi({
      ...defaultRoutes,
      "/me": () => json({ email: "admin@example.com", role: "admin" }),
    })
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("tab", { name: "Library" }))
    expect(
      await screen.findByRole("button", { name: "Ingest sources" }),
    ).toBeInTheDocument()
  })

  it("hides the ingest action from non-admins", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderPage()

    await user.click(await screen.findByRole("tab", { name: "Library" }))
    expect(
      await screen.findByRole("table", { name: "Cached documents" }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Ingest sources" }),
    ).not.toBeInTheDocument()
  })
})
