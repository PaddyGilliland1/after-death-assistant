/*
  Estate accounts export action tests over a mocked fetch: the button
  posts to /exports/estate-accounts and the success toast offers a
  Download action to the returned document; viewers see nothing.
  Fixtures use synthetic data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Toaster } from "@/components/ui/sonner"

import { AccountsExportActions } from "./export-actions"

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

function stubPointerCapture() {
  /* jsdom has no pointer capture; sonner's swipe handling needs these. */
  window.Element.prototype.setPointerCapture = vi.fn()
  window.Element.prototype.releasePointerCapture = vi.fn()
  window.Element.prototype.hasPointerCapture = vi.fn(() => false)
}

function stubMatchMedia() {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  )
}

function renderActions() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
        <Toaster />
      </QueryClientProvider>
    )
  }
  return render(<AccountsExportActions />, { wrapper: Wrapper })
}

beforeEach(() => {
  stubMatchMedia()
  stubPointerCapture()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("AccountsExportActions", () => {
  it("exports the estate accounts and offers a download toast", async () => {
    const openSpy = vi.fn()
    vi.stubGlobal("open", openSpy)
    const calls = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "POST /exports/estate-accounts": () =>
        json({ id: "doc-4", title: "Estate accounts" }, 201),
    })
    const user = userEvent.setup()
    renderActions()

    await user.click(
      await screen.findByRole("button", {
        name: "Export estate accounts PDF",
      }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === "/exports/estate-accounts",
        ),
      ).toBe(true)
    })

    expect(
      await screen.findByText(
        "Estate accounts PDF saved to the documents vault.",
      ),
    ).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Download" }))
    expect(openSpy).toHaveBeenCalledWith(
      expect.stringContaining("/documents/doc-4/download"),
      "_blank",
      "noopener",
    )
  })

  it("renders nothing for a viewer", async () => {
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderActions()

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Export estate accounts PDF" }),
      ).not.toBeInTheDocument()
    })
  })
})
