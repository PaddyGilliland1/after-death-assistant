/*
  IHT workbench tests over a mocked fetch: the latest assessment renders
  with figures exactly as returned plus the filing badges, Recompute
  fires POST /iht/recompute, and the estate settings form serialises the
  tri-state claims_rnrb correctly (null, true, false).
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import IhtPage from "./index"

const assessment = {
  id: "a1",
  estate_id: "e1",
  created_at: "2026-07-01T10:00:00Z",
  constants_version: "EW-2026-27",
  jurisdiction_code: "EW",
  inputs: {
    net_value: "2350000.00",
    tnrb_pct: "0",
    trnrb_pct: "0",
    residence_to_descendants_value: "0",
  },
  nrb: "325000.00",
  rnrb_max: "0.00",
  rnrb: "0.00",
  allowance: "325000.00",
  taxable: "2025000.00",
  rate: "0.40",
  tax: "810000.00",
  is_excepted: false,
  must_file_iht400: true,
  required_schedules: ["IHT405", "IHT406"],
}

const schedules = {
  assessment_id: "a1",
  assessed_at: "2026-07-01T10:00:00Z",
  must_file_iht400: true,
  schedules: [
    { code: "IHT405", reason: "The estate includes land or buildings." },
    {
      code: "IHT406",
      reason:
        "The estate includes bank or building society accounts or NS&I holdings.",
    },
  ],
}

// Synthetic estate settings; no personal data in fixtures.
const estateSettings = {
  id: "e1",
  name: "Estate under administration",
  date_of_death: "2026-01-15",
  grant_date: null,
  constants_version: "EW-2026-27",
  nrb: "325000.00",
  rnrb: "175000.00",
  taper_threshold: "2000000.00",
  tnrb_pct: "0",
  trnrb_pct: "0",
  residence_to_descendants_value: null,
  charity_share_pct: "0",
  claims_rnrb: null,
  gifts_with_reservation: null,
  foreign_assets_value: null,
  trust_property_value: null,
  specified_transfers_value: null,
  created_at: "2026-02-01T00:00:00Z",
  updated_at: "2026-02-01T00:00:00Z",
}

const me = { email: "executor.one@example.com", role: "executor" }

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type RouteHandler = (init?: RequestInit) => Response

/** Routes keyed by "METHOD /path"; a bare "/path" matches any method. */
function mockApi(routes: Record<string, RouteHandler>) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname
      const method = init?.method ?? "GET"
      const handler = routes[`${method} ${path}`] ?? routes[path]
      return handler ? handler(init) : json({ detail: "Not found" }, 404)
    },
  )
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

function defaultRoutes(): Record<string, RouteHandler> {
  return {
    "/me": () => json(me),
    "/iht/assessment": () => json(assessment),
    "/iht/schedules": () => json(schedules),
    "/estate": () => json(estateSettings),
    "POST /iht/recompute": () => json(assessment),
    "PUT /estate": () => json(estateSettings),
  }
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
  return render(<IhtPage />, { wrapper: Wrapper })
}

function lastRequestBody(
  fetchMock: ReturnType<typeof mockApi>,
  method: string,
  path: string,
): unknown {
  const call = [...fetchMock.mock.calls]
    .reverse()
    .find(
      ([input, init]) =>
        (init?.method ?? "GET") === method &&
        new URL(String(input)).pathname === path,
    )
  expect(call).toBeDefined()
  return JSON.parse(String(call?.[1]?.body))
}

/** Opens the settings dialog and returns userEvent plus the dialog. */
async function openSettings(fetchMock: ReturnType<typeof mockApi>) {
  renderPage()
  const user = userEvent.setup({ pointerEventsCheck: 0 })
  await user.click(
    await screen.findByRole("button", { name: /estate settings/i }),
  )
  const dialog = await screen.findByRole("dialog", {
    name: /estate settings/i,
  })
  return { user, dialog, fetchMock }
}

async function saveSettings(
  user: ReturnType<typeof userEvent.setup>,
  dialog: HTMLElement,
) {
  await user.click(
    within(dialog).getByRole("button", { name: /save settings/i }),
  )
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("IhtPage", () => {
  it("renders the latest assessment with exact figures and badges", async () => {
    mockApi(defaultRoutes())
    renderPage()

    expect(await screen.findByText("£2,350,000.00")).toBeInTheDocument()
    // The allowance figure also appears in its own breakdown description.
    expect(screen.getAllByText(/£325,000\.00/).length).toBeGreaterThan(0)
    expect(screen.getByText("£2,025,000.00")).toBeInTheDocument()
    expect(screen.getByText("40%")).toBeInTheDocument()
    expect(screen.getByText("£810,000.00")).toBeInTheDocument()

    expect(screen.getByText("IHT400 required")).toBeInTheDocument()
    expect(screen.getByText("Not an excepted estate")).toBeInTheDocument()
    // Net value 2,350,000 exceeds the taper threshold of 2,000,000.
    expect(await screen.findByText("RNRB taper applied")).toBeInTheDocument()

    expect(screen.getByText("IHT405")).toBeInTheDocument()
    expect(
      screen.getByText("The estate includes land or buildings."),
    ).toBeInTheDocument()

    expect(screen.getByRole("note")).toHaveTextContent(
      "This tool informs and drafts; it is not tax advice.",
    )
  })

  it("degrades calmly when no assessment exists yet", async () => {
    mockApi({
      "/me": () => json(me),
      "/estate": () => json(estateSettings),
    })
    renderPage()

    expect(await screen.findByRole("status")).toHaveTextContent(
      "No assessment has been produced yet.",
    )
  })

  it("hides the write actions from viewers", async () => {
    mockApi({
      ...defaultRoutes(),
      "/me": () => json({ email: "viewer@example.com", role: "viewer" }),
    })
    renderPage()

    await screen.findByText("£810,000.00")
    expect(
      screen.queryByRole("button", { name: /recompute/i }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: /estate settings/i }),
    ).not.toBeInTheDocument()
  })

  it("fires POST /iht/recompute from the Recompute action", async () => {
    const fetchMock = mockApi(defaultRoutes())
    renderPage()
    const user = userEvent.setup({ pointerEventsCheck: 0 })

    await user.click(await screen.findByRole("button", { name: /^recompute$/i }))

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some(
          ([input, init]) =>
            init?.method === "POST" &&
            new URL(String(input)).pathname === "/iht/recompute",
        ),
      ).toBe(true)
    })
  })

  it("serialises an untouched claims_rnrb as null (derive automatically)", async () => {
    const { user, dialog, fetchMock } = await openSettings(
      mockApi(defaultRoutes()),
    )

    await saveSettings(user, dialog)

    await waitFor(() => {
      const body = lastRequestBody(fetchMock, "PUT", "/estate") as Record<
        string,
        unknown
      >
      expect(body.claims_rnrb).toBeNull()
      // Blank excepted-estate facts serialise as null (unknown) too.
      expect(body.gifts_with_reservation).toBeNull()
      expect(body.foreign_assets_value).toBeNull()
    })
  })

  it("serialises claims_rnrb Yes as true", async () => {
    const { user, dialog, fetchMock } = await openSettings(
      mockApi(defaultRoutes()),
    )

    await user.selectOptions(
      within(dialog).getByLabelText(/residence nil rate band claim/i),
      "yes",
    )
    await saveSettings(user, dialog)

    await waitFor(() => {
      const body = lastRequestBody(fetchMock, "PUT", "/estate") as Record<
        string,
        unknown
      >
      expect(body.claims_rnrb).toBe(true)
    })
  })

  it("serialises claims_rnrb No as false", async () => {
    const { user, dialog, fetchMock } = await openSettings(
      mockApi(defaultRoutes()),
    )

    await user.selectOptions(
      within(dialog).getByLabelText(/residence nil rate band claim/i),
      "no",
    )
    await saveSettings(user, dialog)

    await waitFor(() => {
      const body = lastRequestBody(fetchMock, "PUT", "/estate") as Record<
        string,
        unknown
      >
      expect(body.claims_rnrb).toBe(false)
    })
  })
})
