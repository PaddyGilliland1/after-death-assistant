/*
  Knowledge chat tests over a mocked fetch: a loaded thread renders user
  and assistant messages with message-scoped citation links, cited and
  related sources are labelled separately with the pinned badge and
  quotes, posting sends no conversation_id first and the returned id on
  the follow-up, a viewer sees a read-only note instead of the input,
  a 503 shows the not-configured message, and archiving sends the reason.
  Fixtures use example.com data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import { AskSection } from "./ask-section"

const CONV_ID = "11111111-1111-4111-8111-111111111111"
const USER_MSG_ID = "aaaaaaaa-1111-4111-8111-111111111111"
const ASSISTANT_MSG_ID = "bbbbbbbb-1111-4111-8111-111111111111"

const conversation = {
  id: CONV_ID,
  title: "IHT400 timing",
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:05:00Z",
}

const thread = [
  {
    id: USER_MSG_ID,
    role: "user",
    content: "When is IHT400 needed?",
    sources_cited: [],
    related_sources: [],
    created_at: "2026-07-01T10:00:00Z",
  },
  {
    id: ASSISTANT_MSG_ID,
    role: "assistant",
    content:
      "Form IHT400 is needed when the estate is not an excepted estate [1].\n\n" +
      "What the retrieved guidance does not cover\n\n" +
      "The retrieved guidance does not cover Scottish confirmation.",
    sources_cited: [
      {
        n: 1,
        doc_title: "IHT400 notes",
        source_url: "https://example.com/iht400-notes",
        licence: "OGL v3",
        fetch_date: "2026-06-01",
        quotes: [
          "You must send form IHT400 when the estate is not an excepted estate.",
        ],
        relation: "pinned",
      },
    ],
    related_sources: [
      {
        n: null,
        doc_title: "IHT400 calculation",
        source_url: "https://example.com/iht400-calc",
        licence: "OGL v3",
        fetch_date: "2026-06-01",
        quotes: [],
        relation: "retrieved",
      },
    ],
    created_at: "2026-07-01T10:05:00Z",
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
  "GET /knowledge/chats": () => json([conversation]),
  [`GET /knowledge/chats/${CONV_ID}/messages`]: () => json(thread),
}

function renderSection() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
  return render(<AskSection />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AskSection", () => {
  it("renders a loaded thread with message-scoped citation links", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole("button", { name: /IHT400 timing/ }))

    expect(
      await screen.findByText("When is IHT400 needed?"),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/Form IHT400 is needed when the estate/),
    ).toBeInTheDocument()

    const citation = screen.getByRole("link", {
      name: "Citation 1: IHT400 notes",
    })
    expect(citation).toHaveAttribute(
      "href",
      `#msg-${ASSISTANT_MSG_ID}-source-1`,
    )

    /* The caveats section stays visible below the body. */
    expect(
      screen.getByText(/does not cover Scottish confirmation/),
    ).toBeInTheDocument()
  })

  it("labels cited and related sources separately, with the pinned badge and quotes", async () => {
    mockApi(defaultRoutes)
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole("button", { name: /IHT400 timing/ }))

    const cited = await screen.findByRole("list", { name: "Sources cited" })
    expect(
      within(cited).getByRole("link", { name: /IHT400 notes/ }),
    ).toHaveAttribute("href", "https://example.com/iht400-notes")
    expect(
      within(cited).getByText("Pinned from earlier"),
    ).toBeInTheDocument()
    expect(
      within(cited).getByText(/You must send form IHT400 when the estate/),
    ).toBeInTheDocument()

    const related = screen.getByRole("list", {
      name: "Also retrieved, not cited",
    })
    expect(
      within(related).getByRole("link", { name: /IHT400 calculation/ }),
    ).toHaveAttribute("href", "https://example.com/iht400-calc")
    /* Related sources carry no citation number and no quotes. */
    expect(
      within(related).queryByText(/You must send form IHT400/),
    ).not.toBeInTheDocument()
  })

  it("posts without a conversation_id first, then with it on the follow-up", async () => {
    const NEW_CONV_ID = "22222222-2222-4222-8222-222222222222"
    /* The mock keeps the server-side thread so the refetch after each
       turn returns the accumulated messages, as the real backend does. */
    const serverThread: unknown[] = []
    let turn = 0
    const calls = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "GET /knowledge/chats": () => json([]),
      [`GET /knowledge/chats/${NEW_CONV_ID}/messages`]: () =>
        json(serverThread),
      "POST /knowledge/chat": (body) => {
        turn += 1
        const question = (body as { question: string }).question
        const message = {
          id: `cccccccc-1111-4111-8111-11111111111${turn}`,
          role: "assistant",
          content: `Answer number ${turn}.`,
          sources_cited: [],
          related_sources: [],
          created_at: "2026-07-01T10:05:00Z",
        }
        serverThread.push(
          {
            id: `dddddddd-1111-4111-8111-11111111111${turn}`,
            role: "user",
            content: question,
            sources_cited: [],
            related_sources: [],
            created_at: "2026-07-01T10:04:00Z",
          },
          message,
        )
        return json({ conversation_id: NEW_CONV_ID, message })
      },
    })
    const user = userEvent.setup()
    renderSection()

    const textarea = await screen.findByLabelText("Your question")
    await user.type(textarea, "When is IHT400 needed?")
    await user.click(screen.getByRole("button", { name: "Ask" }))

    expect(await screen.findByText("Answer number 1.")).toBeInTheDocument()
    const firstPost = calls.find(
      (call) => call.method === "POST" && call.path === "/knowledge/chat",
    )
    expect(firstPost?.body).toEqual({ question: "When is IHT400 needed?" })

    /* The follow-up submits on Enter and carries the conversation id. */
    await user.type(
      screen.getByLabelText("Your question"),
      "What about jointly owned assets?{Enter}",
    )

    await waitFor(() => {
      expect(
        calls.filter(
          (call) => call.method === "POST" && call.path === "/knowledge/chat",
        ),
      ).toHaveLength(2)
    })
    const secondPost = calls.filter(
      (call) => call.method === "POST" && call.path === "/knowledge/chat",
    )[1]
    expect(secondPost.body).toEqual({
      conversation_id: NEW_CONV_ID,
      question: "What about jointly owned assets?",
    })
  })

  it("shows a viewer the read-only note and no question input", async () => {
    mockApi({
      ...defaultRoutes,
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderSection()

    expect(
      await screen.findByText(/Your access is read only/),
    ).toBeInTheDocument()
    expect(screen.queryByLabelText("Your question")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Ask" }),
    ).not.toBeInTheDocument()
  })

  it("shows the not-configured message on a 503", async () => {
    mockApi({
      ...defaultRoutes,
      "GET /knowledge/chats": () => json([]),
      "POST /knowledge/chat": () =>
        json({ detail: "ANTHROPIC_API_KEY is not configured" }, 503),
    })
    const user = userEvent.setup()
    renderSection()

    await user.type(
      await screen.findByLabelText("Your question"),
      "Anything at all?",
    )
    await user.click(screen.getByRole("button", { name: "Ask" }))

    expect(
      await screen.findByText("The assistant is not configured yet."),
    ).toBeInTheDocument()
  })

  it("archives the active conversation with a reason", async () => {
    const calls = mockApi({
      ...defaultRoutes,
      [`DELETE /knowledge/chats/${CONV_ID}`]: () => json(conversation),
    })
    const user = userEvent.setup()
    renderSection()

    await user.click(await screen.findByRole("button", { name: /IHT400 timing/ }))
    await user.click(
      await screen.findByRole("button", { name: "Archive conversation" }),
    )
    await user.type(
      await screen.findByLabelText("Reason for archiving"),
      "Asked in error",
    )
    await user.click(screen.getByRole("button", { name: "Archive" }))

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "DELETE" &&
            call.path === `/knowledge/chats/${CONV_ID}`,
        ),
      ).toBe(true)
    })
    const archiveCall = calls.find(
      (call) =>
        call.method === "DELETE" &&
        call.path === `/knowledge/chats/${CONV_ID}`,
    )
    expect(archiveCall?.body).toEqual({ reason: "Asked in error" })
  })
})
