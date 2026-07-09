/*
  IHT export action tests over a mocked fetch: the export button posts
  to /exports/iht-draft with no body (the server reads the latest
  approved forms draft itself); the success toast offers a Download
  action wired to the returned document's download URL; a 404 (no
  approved draft yet) explains what to do; viewers see no buttons.
  Fixtures use synthetic data only.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { Toaster } from "@/components/ui/sonner"

import { IhtExportActions } from "./export-actions"

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
  routes: Record<string, () => Response>,
): RecordedCall[] {
  const calls: RecordedCall[] = []
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(String(input))
      const method = init?.method ?? "GET"
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      calls.push({ method, path: url.pathname, body })
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
  return render(<IhtExportActions />, { wrapper: Wrapper })
}

beforeEach(() => {
  stubMatchMedia()
  stubPointerCapture()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("IhtExportActions", () => {
  it("exports the IHT draft and offers a download toast", async () => {
    const openSpy = vi.fn()
    vi.stubGlobal("open", openSpy)
    const calls = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "POST /exports/iht-draft": () =>
        json({ id: "doc-9", title: "IHT400 draft export" }, 201),
    })
    const user = userEvent.setup()
    renderActions()

    await user.click(
      await screen.findByRole("button", { name: "Export IHT draft PDF" }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" && call.path === "/exports/iht-draft",
        ),
      ).toBe(true)
    })

    /* No body: the server reads the latest approved forms draft itself. */
    const post = calls.find(
      (call) => call.method === "POST" && call.path === "/exports/iht-draft",
    )
    expect(post?.body).toBeUndefined()

    expect(
      await screen.findByText("IHT draft PDF saved to the documents vault."),
    ).toBeInTheDocument()

    await user.click(screen.getByRole("button", { name: "Download" }))
    expect(openSpy).toHaveBeenCalledWith(
      expect.stringContaining("/documents/doc-9/download"),
      "_blank",
      "noopener",
    )
  })

  it("explains when no approved forms draft exists to export", async () => {
    mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "POST /exports/iht-draft": () =>
        json({ detail: "No approved forms draft exists." }, 404),
    })
    const user = userEvent.setup()
    renderActions()

    await user.click(
      await screen.findByRole("button", { name: "Export IHT draft PDF" }),
    )

    expect(
      await screen.findByText(
        "No approved IHT form draft to export yet. Draft the IHT400 pack on the Drafts page and approve it first.",
      ),
    ).toBeInTheDocument()
  })

  it("offers the clearance draft export", async () => {
    const calls = mockApi({
      "/me": () => json({ email: "executor@example.com", role: "executor" }),
      "POST /exports/clearance-draft": () =>
        json({ id: "doc-10", title: "Clearance draft" }, 201),
    })
    const user = userEvent.setup()
    renderActions()

    await user.click(
      await screen.findByRole("button", {
        name: "Export clearance draft PDF",
      }),
    )

    await waitFor(() => {
      expect(
        calls.some(
          (call) =>
            call.method === "POST" &&
            call.path === "/exports/clearance-draft",
        ),
      ).toBe(true)
    })
  })

  it("renders nothing for a viewer", async () => {
    mockApi({
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderActions()

    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Export IHT draft PDF" }),
      ).not.toBeInTheDocument()
    })
  })
})
