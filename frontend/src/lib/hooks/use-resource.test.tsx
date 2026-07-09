/*
  CRUD hook tests over a mocked fetch. The fake server keeps a widgets
  array in memory so the tests can prove that mutations invalidate the
  list query and it refetches fresh data.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import {
  resourceKeys,
  useArchiveResource,
  useCreateResource,
  useResource,
  useResourceList,
  useUpdateResource,
} from "./use-resource"

interface Widget {
  id: string
  name: string
  archive_reason?: string | null
}

let widgets: Widget[]
let fetchMock: ReturnType<typeof vi.fn>

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

function installFetchMock() {
  fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input))
    const method = init?.method ?? "GET"
    const path = url.pathname

    if (method === "GET" && path === "/widgets") {
      return json(widgets)
    }
    const detailMatch = path.match(/^\/widgets\/([^/]+)$/)
    if (method === "GET" && detailMatch) {
      const found = widgets.find((widget) => widget.id === detailMatch[1])
      return found ? json(found) : json({ detail: "Not found" }, 404)
    }
    if (method === "POST" && path === "/widgets") {
      const body = JSON.parse(String(init?.body)) as Partial<Widget>
      const created: Widget = { id: String(widgets.length + 1), name: "", ...body }
      widgets = [...widgets, created]
      return json(created, 201)
    }
    if (method === "PATCH" && detailMatch) {
      const body = JSON.parse(String(init?.body)) as Partial<Widget>
      widgets = widgets.map((widget) =>
        widget.id === detailMatch[1] ? { ...widget, ...body } : widget,
      )
      return json(widgets.find((widget) => widget.id === detailMatch[1]))
    }
    if (method === "DELETE" && detailMatch) {
      const body = JSON.parse(String(init?.body)) as { reason: string }
      widgets = widgets.filter((widget) => widget.id !== detailMatch[1])
      return json({ archived: true, reason: body.reason })
    }
    return json({ detail: "Not found" }, 404)
  })
  vi.stubGlobal("fetch", fetchMock)
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    )
  }
  return { queryClient, Wrapper }
}

beforeEach(() => {
  widgets = [{ id: "1", name: "Sample record" }]
  installFetchMock()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("useResourceList", () => {
  it("lists a resource", async () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useResourceList<Widget>("/widgets"), {
      wrapper: Wrapper,
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual([{ id: "1", name: "Sample record" }])
  })

  it("resolves to null when the endpoint is not implemented yet", async () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(
      () => useResourceList<Widget>("/not-built-yet"),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toBeNull()
  })
})

describe("useResource", () => {
  it("fetches a single record by id", async () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(() => useResource<Widget>("/widgets", "1"), {
      wrapper: Wrapper,
    })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual({ id: "1", name: "Sample record" })
  })

  it("stays idle without an id", () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(
      () => useResource<Widget>("/widgets", undefined),
      { wrapper: Wrapper },
    )
    expect(result.current.fetchStatus).toBe("idle")
  })
})

describe("mutations invalidate the resource cache", () => {
  it("create refetches the list with the new record", async () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(
      () => ({
        list: useResourceList<Widget>("/widgets"),
        create: useCreateResource<Widget>("/widgets"),
      }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.list.isSuccess).toBe(true))
    expect(result.current.list.data).toHaveLength(1)

    result.current.create.mutate({ name: "Second record" })

    await waitFor(() => expect(result.current.list.data).toHaveLength(2))
    expect(result.current.list.data?.[1]).toMatchObject({
      name: "Second record",
    })
  })

  it("update refetches list and detail", async () => {
    const { Wrapper, queryClient } = createWrapper()
    const { result } = renderHook(
      () => ({
        list: useResourceList<Widget>("/widgets"),
        detail: useResource<Widget>("/widgets", "1"),
        update: useUpdateResource<Widget>("/widgets"),
      }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.detail.isSuccess).toBe(true))

    result.current.update.mutate({ id: "1", data: { name: "Renamed record" } })

    await waitFor(() =>
      expect(result.current.detail.data?.name).toBe("Renamed record"),
    )
    expect(
      queryClient.getQueryData(resourceKeys.detail("/widgets", "1")),
    ).toMatchObject({ name: "Renamed record" })
  })

  it("archive sends DELETE with the reason and removes the record from the list", async () => {
    const { Wrapper } = createWrapper()
    const { result } = renderHook(
      () => ({
        list: useResourceList<Widget>("/widgets"),
        archive: useArchiveResource("/widgets"),
      }),
      { wrapper: Wrapper },
    )

    await waitFor(() => expect(result.current.list.data).toHaveLength(1))

    result.current.archive.mutate({ id: "1", reason: "Recorded in error" })

    await waitFor(() => expect(result.current.list.data).toHaveLength(0))

    const archiveCall = fetchMock.mock.calls.find(
      ([input, init]) =>
        String(input).endsWith("/widgets/1") && init?.method === "DELETE",
    )
    expect(archiveCall).toBeDefined()
    expect(JSON.parse(String(archiveCall?.[1]?.body))).toEqual({
      reason: "Recorded in error",
    })
  })
})
