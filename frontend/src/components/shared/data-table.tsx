/*
  A plain, typed data table over the shadcn table primitives. No TanStack
  Table: sorting, filtering and pagination are simple local state over the
  rows given. Column defs carry a value accessor used for sorting and
  filtering, plus an optional kind (money, date, badge) or a custom render.

  Accessibility: sortable headers are buttons inside th elements, with
  aria-sort on the active column; the filter input has a label; pagination
  controls are labelled buttons inside a nav landmark.
*/

import * as React from "react"
import { ArrowDown, ArrowUp, ArrowUpDown, Inbox } from "lucide-react"

import { formatDate, formatMoney } from "@/components/shared/formatters"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { cn } from "@/lib/utils"

export type CellKind = "text" | "money" | "date" | "badge"

export type BadgeVariant = "default" | "secondary" | "destructive" | "outline"

export interface DataTableColumn<T> {
  /** Stable identifier for the column, used for sort state and React keys. */
  key: string
  /** Header label. */
  header: string
  /**
   * Raw value for the cell. Used for display (via kind), sorting and
   * filtering. Money values may be the API's decimal strings.
   */
  value: (row: T) => string | number | null | undefined
  /** Built-in renderer: money and date format en-GB, badge wraps in a Badge. */
  kind?: CellKind
  /** Badge variant when kind is "badge". Defaults to "secondary". */
  badgeVariant?: (row: T) => BadgeVariant
  /** Custom cell renderer. Overrides kind for display; value still sorts. */
  render?: (row: T) => React.ReactNode
  /** Whether the column can be sorted. Defaults to true. */
  sortable?: boolean
  /** Text alignment. Money columns default to right. */
  align?: "left" | "right"
}

export interface DataTableProps<T> {
  columns: DataTableColumn<T>[]
  /** Rows to show. Pass undefined while loading. */
  rows: T[] | null | undefined
  /** Stable key for each row, usually the record id. */
  rowKey: (row: T) => string
  /** Shows a loading skeleton instead of rows. */
  isLoading?: boolean
  /** Rows per page. Defaults to 10. */
  pageSize?: number
  /** Shows a text filter above the table. Defaults to true. */
  filterable?: boolean
  /** Label for the filter input, also its placeholder. */
  filterLabel?: string
  /** Heading shown when there are no rows at all. */
  emptyTitle?: string
  /** Supporting copy for the empty state. */
  emptyMessage?: string
  /** Accessible description of the table, linked via aria-label. */
  label?: string
  /** Called when a row is clicked or activated with the keyboard. */
  onRowClick?: (row: T) => void
}

type SortDirection = "asc" | "desc"

function compareValues(
  a: string | number | null | undefined,
  b: string | number | null | undefined,
  direction: SortDirection,
): number {
  // Missing values always sort last, whichever the direction.
  const aMissing = a === null || a === undefined || a === ""
  const bMissing = b === null || b === undefined || b === ""
  if (aMissing && bMissing) return 0
  if (aMissing) return 1
  if (bMissing) return -1

  const aNum = typeof a === "number" ? a : Number(a)
  const bNum = typeof b === "number" ? b : Number(b)
  const base =
    !Number.isNaN(aNum) && !Number.isNaN(bNum)
      ? aNum - bNum
      : String(a).localeCompare(String(b), "en-GB", { sensitivity: "base" })

  return direction === "asc" ? base : -base
}

function defaultCell<T>(column: DataTableColumn<T>, row: T): React.ReactNode {
  if (column.render) return column.render(row)

  const value = column.value(row)
  if (value === null || value === undefined || value === "") {
    return <span aria-hidden="true">&ndash;</span>
  }

  switch (column.kind) {
    case "money":
      return <span className="tabular-nums">{formatMoney(value)}</span>
    case "date":
      return formatDate(String(value))
    case "badge":
      return (
        <Badge variant={column.badgeVariant?.(row) ?? "secondary"}>
          {String(value)}
        </Badge>
      )
    default:
      return String(value)
  }
}

function columnAlignment<T>(column: DataTableColumn<T>): "left" | "right" {
  return column.align ?? (column.kind === "money" ? "right" : "left")
}

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  isLoading = false,
  pageSize = 10,
  filterable = true,
  filterLabel = "Filter records",
  emptyTitle = "Nothing recorded here yet.",
  emptyMessage = "Records will appear here as they are added.",
  label,
  onRowClick,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = React.useState<string | null>(null)
  const [sortDirection, setSortDirection] =
    React.useState<SortDirection>("asc")
  const [filter, setFilter] = React.useState("")
  const [page, setPage] = React.useState(0)

  const filterId = React.useId()

  const allRows = React.useMemo(() => rows ?? [], [rows])

  const filteredRows = React.useMemo(() => {
    const needle = filter.trim().toLowerCase()
    if (!needle) return allRows
    return allRows.filter((row) =>
      columns.some((column) => {
        const value = column.value(row)
        if (value === null || value === undefined) return false
        return String(value).toLowerCase().includes(needle)
      }),
    )
  }, [allRows, columns, filter])

  const sortedRows = React.useMemo(() => {
    if (!sortKey) return filteredRows
    const column = columns.find((candidate) => candidate.key === sortKey)
    if (!column) return filteredRows
    return [...filteredRows].sort((a, b) =>
      compareValues(column.value(a), column.value(b), sortDirection),
    )
  }, [columns, filteredRows, sortDirection, sortKey])

  const pageCount = Math.max(1, Math.ceil(sortedRows.length / pageSize))
  const safePage = Math.min(page, pageCount - 1)
  const pageRows = sortedRows.slice(
    safePage * pageSize,
    (safePage + 1) * pageSize,
  )

  function toggleSort(key: string) {
    if (sortKey === key) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDirection("asc")
    }
    setPage(0)
  }

  function handleFilterChange(value: string) {
    setFilter(value)
    setPage(0)
  }

  if (!isLoading && allRows.length === 0) {
    return (
      <div className="flex flex-col items-center gap-3 rounded-xl border py-16 text-center">
        <Inbox aria-hidden="true" className="size-8 text-muted-foreground" />
        <p className="font-medium">{emptyTitle}</p>
        <p className="max-w-sm text-sm text-muted-foreground">
          {emptyMessage}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {filterable && !isLoading ? (
        <div className="max-w-xs">
          <label htmlFor={filterId} className="sr-only">
            {filterLabel}
          </label>
          <Input
            id={filterId}
            type="search"
            value={filter}
            placeholder={filterLabel}
            onChange={(event) => handleFilterChange(event.target.value)}
          />
        </div>
      ) : null}

      <div className="rounded-xl border" aria-busy={isLoading}>
        <Table aria-label={label}>
          <TableHeader>
            <TableRow>
              {columns.map((column) => {
                const sortable = column.sortable ?? true
                const isSorted = sortKey === column.key
                const align = columnAlignment(column)
                return (
                  <TableHead
                    key={column.key}
                    aria-sort={
                      isSorted
                        ? sortDirection === "asc"
                          ? "ascending"
                          : "descending"
                        : undefined
                    }
                    className={cn(align === "right" && "text-right")}
                  >
                    {sortable ? (
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        className={cn(
                          "inline-flex min-h-9 items-center gap-1 rounded-md font-medium hover:text-foreground/80 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring",
                          align === "right" && "flex-row-reverse",
                        )}
                      >
                        {column.header}
                        {isSorted ? (
                          sortDirection === "asc" ? (
                            <ArrowUp aria-hidden="true" className="size-3.5" />
                          ) : (
                            <ArrowDown
                              aria-hidden="true"
                              className="size-3.5"
                            />
                          )
                        ) : (
                          <ArrowUpDown
                            aria-hidden="true"
                            className="size-3.5 text-muted-foreground"
                          />
                        )}
                      </button>
                    ) : (
                      column.header
                    )}
                  </TableHead>
                )
              })}
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading
              ? Array.from({ length: Math.min(pageSize, 5) }, (_, index) => (
                  <TableRow key={`skeleton-${index}`}>
                    {columns.map((column) => (
                      <TableCell key={column.key}>
                        <Skeleton className="h-4 w-full max-w-32" />
                      </TableCell>
                    ))}
                  </TableRow>
                ))
              : pageRows.map((row) => (
                  <TableRow
                    key={rowKey(row)}
                    onClick={onRowClick ? () => onRowClick(row) : undefined}
                    onKeyDown={
                      onRowClick
                        ? (event) => {
                            if (event.key === "Enter" || event.key === " ") {
                              event.preventDefault()
                              onRowClick(row)
                            }
                          }
                        : undefined
                    }
                    tabIndex={onRowClick ? 0 : undefined}
                    className={cn(
                      onRowClick &&
                        "cursor-pointer focus-visible:outline-2 focus-visible:outline-ring",
                    )}
                  >
                    {columns.map((column) => (
                      <TableCell
                        key={column.key}
                        className={cn(
                          columnAlignment(column) === "right" && "text-right",
                        )}
                      >
                        {defaultCell(column, row)}
                      </TableCell>
                    ))}
                  </TableRow>
                ))}
            {!isLoading && pageRows.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="py-8 text-center text-muted-foreground"
                >
                  No records match the filter.
                </TableCell>
              </TableRow>
            ) : null}
          </TableBody>
        </Table>
      </div>

      {!isLoading && pageCount > 1 ? (
        <nav
          aria-label="Pagination"
          className="flex items-center justify-between gap-4"
        >
          <p className="text-sm text-muted-foreground" aria-live="polite">
            Page {safePage + 1} of {pageCount}
          </p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((current) => Math.max(0, current - 1))}
              disabled={safePage === 0}
            >
              Previous
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() =>
                setPage((current) => Math.min(pageCount - 1, current + 1))
              }
              disabled={safePage >= pageCount - 1}
            >
              Next
            </Button>
          </div>
        </nav>
      ) : null}
    </div>
  )
}
