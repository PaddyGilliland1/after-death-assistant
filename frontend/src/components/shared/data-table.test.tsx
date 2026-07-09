import { render, screen, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it } from "vitest"

import { DataTable, type DataTableColumn } from "./data-table"

interface FixtureRow {
  id: string
  name: string
  amount: string | null
  date: string | null
  status: string
}

const columns: DataTableColumn<FixtureRow>[] = [
  { key: "name", header: "Name", value: (row) => row.name },
  { key: "amount", header: "Amount", value: (row) => row.amount, kind: "money" },
  { key: "date", header: "Date", value: (row) => row.date, kind: "date" },
  {
    key: "status",
    header: "Status",
    value: (row) => row.status,
    kind: "badge",
    sortable: false,
  },
]

const rows: FixtureRow[] = [
  {
    id: "1",
    name: "Alex Example",
    amount: "250.00",
    date: "2026-01-15",
    status: "open",
  },
  {
    id: "2",
    name: "Billie Example",
    amount: "1000.00",
    date: "2026-02-01",
    status: "done",
  },
  {
    id: "3",
    name: "Charlie Example",
    amount: null,
    date: null,
    status: "open",
  },
]

function renderTable(props: Partial<React.ComponentProps<typeof DataTable<FixtureRow>>> = {}) {
  return render(
    <DataTable<FixtureRow>
      columns={columns}
      rows={rows}
      rowKey={(row) => row.id}
      label="Fixtures"
      {...props}
    />,
  )
}

function firstBodyRowText(): string {
  const table = screen.getByRole("table", { name: "Fixtures" })
  const bodyRows = within(table).getAllByRole("row").slice(1)
  return bodyRows[0].textContent ?? ""
}

describe("DataTable", () => {
  it("renders built-in money, date and badge cells", () => {
    renderTable()

    expect(screen.getByText("£250.00")).toBeInTheDocument()
    expect(screen.getByText("15 Jan 2026")).toBeInTheDocument()
    expect(screen.getAllByText("open").length).toBe(2)
  })

  it("sorts by a column, toggling direction, with aria-sort on the header", async () => {
    const user = userEvent.setup()
    renderTable()

    const amountButton = screen.getByRole("button", { name: /Amount/ })
    await user.click(amountButton)

    const amountHeader = screen.getByRole("columnheader", { name: /Amount/ })
    expect(amountHeader).toHaveAttribute("aria-sort", "ascending")
    expect(firstBodyRowText()).toContain("Alex Example")

    await user.click(amountButton)
    expect(amountHeader).toHaveAttribute("aria-sort", "descending")
    // Missing amounts sort last even descending; largest amount first.
    expect(firstBodyRowText()).toContain("Billie Example")
  })

  it("does not offer sorting on columns marked not sortable", () => {
    renderTable()
    expect(
      screen.queryByRole("button", { name: /Status/ }),
    ).not.toBeInTheDocument()
  })

  it("filters rows across columns", async () => {
    const user = userEvent.setup()
    renderTable({ filterLabel: "Filter fixtures" })

    await user.type(screen.getByLabelText("Filter fixtures"), "billie")

    expect(screen.getByText("Billie Example")).toBeInTheDocument()
    expect(screen.queryByText("Alex Example")).not.toBeInTheDocument()

    await user.clear(screen.getByLabelText("Filter fixtures"))
    await user.type(screen.getByLabelText("Filter fixtures"), "zzz")
    expect(screen.getByText("No records match the filter.")).toBeInTheDocument()
  })

  it("paginates with previous and next controls", async () => {
    const user = userEvent.setup()
    renderTable({ pageSize: 2 })

    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument()
    expect(screen.getByText("Alex Example")).toBeInTheDocument()
    expect(screen.queryByText("Charlie Example")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled()

    await user.click(screen.getByRole("button", { name: "Next" }))

    expect(screen.getByText("Page 2 of 2")).toBeInTheDocument()
    expect(screen.getByText("Charlie Example")).toBeInTheDocument()
    expect(screen.queryByText("Alex Example")).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled()
  })

  it("shows a calm empty state when there are no rows", () => {
    renderTable({ rows: [], emptyTitle: "No fixtures recorded yet." })

    expect(screen.getByText("No fixtures recorded yet.")).toBeInTheDocument()
    expect(screen.queryByRole("table")).not.toBeInTheDocument()
  })

  it("shows a loading skeleton while rows load", () => {
    const { container } = renderTable({ rows: undefined, isLoading: true })

    expect(container.querySelector("[aria-busy='true']")).not.toBeNull()
    expect(
      container.querySelectorAll("[data-slot='skeleton']").length,
    ).toBeGreaterThan(0)
  })
})
