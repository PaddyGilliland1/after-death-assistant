/*
  Debtors and creditors module tests over a mocked fetch: the three
  registers render, the create flow POSTs the DebtorCreate payload with
  empty optionals omitted, the safe to distribute banner shows both its
  states, and a viewer sees the tables without any write affordances.
*/

import type { ReactNode } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { afterEach, describe, expect, it, vi } from "vitest"

import DebtorsCreditorsPage from "./index"

const ESTATE_ID = "0e585ba8-9f4d-4f0e-a5b7-000000000002"

const estate = { id: ESTATE_ID, name: "Estate of Alex Example" }

const audit = {
  estate_id: ESTATE_ID,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
  created_by: "alex.example@example.com",
  archived_at: null,
  archive_reason: null,
}

const debtors = [
  {
    id: "d1",
    ...audit,
    source_contact_id: null,
    type: "utility_refund",
    amount_expected: "250.00",
    amount_received: null,
    status: "expected",
    expected_date: "2026-08-01",
    received_into_asset_id: null,
  },
]

const creditors = [
  {
    id: "cr1",
    ...audit,
    creditor_contact_id: null,
    type: "funeral_account",
    amount_claimed: "3200.00",
    amount_agreed: "3150.00",
    amount_paid: null,
    status: "agreed",
    priority_class: "funeral_expenses",
    paid_from_asset_id: null,
  },
]

const notices = [
  {
    id: "n1",
    ...audit,
    gazette_ref: "GAZ-4021987",
    gazette_date: "2026-01-10",
    local_paper: "Example Weekly News",
    local_date: "2026-01-12",
    claim_deadline: "2026-03-13",
    safe_to_distribute: false,
  },
]

const claims = [
  {
    id: "cl1",
    ...audit,
    creditor_notice_id: "n1",
    claimant: "Example Energy Ltd",
    amount: "120.00",
    status: null,
  },
]

const safeYes = {
  safe_to_distribute: true,
  checked_on: "2026-07-06",
  reasons: [
    "All notice claim deadlines have passed and no claims remain open.",
  ],
}

const safeNo = {
  safe_to_distribute: false,
  checked_on: "2026-07-06",
  reasons: [
    "Notice n1 claim deadline 2026-08-13 has not yet passed.",
    "Notice n1 has 1 open claim(s) awaiting resolution.",
  ],
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  })
}

type Handler = (body: unknown) => Response

function mockApi(routes: Record<string, Handler>) {
  const fetchMock = vi.fn(
    async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = new URL(String(input)).pathname
      const method = init?.method ?? "GET"
      const handler = routes[`${method} ${path}`]
      const body = init?.body ? JSON.parse(String(init.body)) : undefined
      return handler ? handler(body) : json({ detail: "Not found" }, 404)
    },
  )
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

function baseRoutes(role: "executor" | "viewer" = "executor") {
  return {
    "GET /me": () => json({ email: "alex.example@example.com", role }),
    "GET /estate": () => json(estate),
    "GET /debtors": () => json(debtors),
    "GET /creditors": () => json(creditors),
    "GET /creditor-notices": () => json(notices),
    "GET /creditor-notices/safe-to-distribute": () => json(safeNo),
    "GET /creditor-notices/n1/claims": () => json(claims),
  } satisfies Record<string, Handler>
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
  return render(<DebtorsCreditorsPage />, { wrapper: Wrapper })
}

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("DebtorsCreditorsPage", () => {
  it("renders the debtors, creditors and notices registers", async () => {
    mockApi(baseRoutes())
    renderPage()

    expect(await screen.findByText("Utility refund")).toBeInTheDocument()
    expect(screen.getByText("£250.00")).toBeInTheDocument()
    expect(await screen.findByText("Funeral account")).toBeInTheDocument()
    expect(screen.getByText("£3,200.00")).toBeInTheDocument()
    expect(screen.getByText("Funeral expenses")).toBeInTheDocument()
    expect(await screen.findByText("GAZ-4021987")).toBeInTheDocument()
    expect(screen.getByText("13 Mar 2026")).toBeInTheDocument()
    // The one unresolved claim shows as an open claims count of 1.
    expect(await screen.findByText("1")).toBeInTheDocument()
  })

  it("shows an amber banner with the reasons when distribution is not safe", async () => {
    mockApi(baseRoutes())
    renderPage()

    expect(
      await screen.findByText("Not yet safe to distribute"),
    ).toBeInTheDocument()
    expect(
      screen.getByText("Notice n1 claim deadline 2026-08-13 has not yet passed."),
    ).toBeInTheDocument()
    expect(
      screen.getByText("Notice n1 has 1 open claim(s) awaiting resolution."),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/not legal or financial advice/),
    ).toBeInTheDocument()
  })

  it("shows a green banner when distribution is safe, still worded as a guard", async () => {
    mockApi({
      ...baseRoutes(),
      "GET /creditor-notices/safe-to-distribute": () => json(safeYes),
    })
    renderPage()

    expect(await screen.findByText("Safe to distribute")).toBeInTheDocument()
    expect(
      screen.getByText(
        "All notice claim deadlines have passed and no claims remain open.",
      ),
    ).toBeInTheDocument()
    expect(
      screen.getByText(/not legal or financial advice/),
    ).toBeInTheDocument()
  })

  it("creates a debtor with the DebtorCreate payload, omitting empty optionals", async () => {
    const postDebtor = vi.fn(() =>
      json({ ...debtors[0], id: "d2", type: "tax_repayment" }, 201),
    )
    mockApi({ ...baseRoutes(), "POST /debtors": postDebtor })

    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    await user.click(await screen.findByRole("button", { name: "Add debtor" }))
    const dialog = await screen.findByRole("dialog")
    await user.type(within(dialog).getByLabelText("Type"), "tax_repayment")
    await user.type(
      within(dialog).getByLabelText(/Amount expected/),
      "250.00",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Save debtor" }),
    )

    await waitFor(() => expect(postDebtor).toHaveBeenCalledTimes(1))
    expect(postDebtor).toHaveBeenCalledWith({
      estate_id: ESTATE_ID,
      type: "tax_repayment",
      amount_expected: "250.00",
    })
  })

  it("lets a write role add a claim and update a claim status from the notice detail", async () => {
    const postClaim = vi.fn(() =>
      json({ ...claims[0], id: "cl2", claimant: "Example Water" }, 201),
    )
    const patchClaim = vi.fn(() =>
      json({ ...claims[0], status: "resolved" }),
    )
    mockApi({
      ...baseRoutes(),
      "POST /creditor-notices/n1/claims": postClaim,
      "PATCH /creditor-notices/n1/claims/cl1": patchClaim,
    })

    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    await user.click(await screen.findByText("GAZ-4021987"))
    const dialog = await screen.findByRole("dialog")
    expect(
      await within(dialog).findByText("Example Energy Ltd"),
    ).toBeInTheDocument()

    // Update the existing claim's status.
    await user.selectOptions(
      within(dialog).getByLabelText(
        "Status of the claim from Example Energy Ltd",
      ),
      "resolved",
    )
    await waitFor(() => expect(patchClaim).toHaveBeenCalledTimes(1))
    expect(patchClaim).toHaveBeenCalledWith({ status: "resolved" })

    // Add a new claim.
    await user.type(
      within(dialog).getByLabelText("Claimant"),
      "Example Water",
    )
    await user.click(
      within(dialog).getByRole("button", { name: "Add claim" }),
    )
    await waitFor(() => expect(postClaim).toHaveBeenCalledTimes(1))
    expect(postClaim).toHaveBeenCalledWith({ claimant: "Example Water" })
  })

  it("hides every write affordance from a viewer", async () => {
    mockApi(baseRoutes("viewer"))
    const user = userEvent.setup({ pointerEventsCheck: 0 })
    renderPage()

    expect(await screen.findByText("Utility refund")).toBeInTheDocument()
    for (const name of ["Add debtor", "Add creditor", "Add notice"]) {
      expect(
        screen.queryByRole("button", { name }),
      ).not.toBeInTheDocument()
    }

    await user.click(screen.getByText("GAZ-4021987"))
    const dialog = await screen.findByRole("dialog")
    expect(
      await within(dialog).findByText("Example Energy Ltd"),
    ).toBeInTheDocument()

    // The claim status is read only and there is no add claim form.
    expect(within(dialog).getByText("Open")).toBeInTheDocument()
    expect(
      within(dialog).queryByLabelText(
        "Status of the claim from Example Energy Ltd",
      ),
    ).not.toBeInTheDocument()
    expect(
      within(dialog).queryByRole("button", { name: "Add claim" }),
    ).not.toBeInTheDocument()
    expect(
      within(dialog).queryByRole("button", { name: "Edit" }),
    ).not.toBeInTheDocument()
    expect(
      within(dialog).queryByRole("button", { name: "Archive" }),
    ).not.toBeInTheDocument()
  })
})
