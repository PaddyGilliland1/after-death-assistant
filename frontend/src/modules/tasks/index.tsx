/*
  Tasks module: the estate to-do list with dependencies. A DataTable with
  status and due-before filters, a create/edit form with checklist editor
  and blocked-by dependency picker, a detail dialog with the comments
  thread and a status select, and archive with a reason.
*/

import * as React from "react"

import { ArchiveDialog } from "@/components/shared/archive-dialog"
import {
  DataTable,
  type DataTableColumn,
} from "@/components/shared/data-table"
import { PageHeader } from "@/components/shared/page-header"
import { Badge } from "@/components/ui/badge"
import { Input } from "@/components/ui/input"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ApiError } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"
import {
  useArchiveResource,
  useCreateResource,
  useResourceList,
  useUpdateResource,
} from "@/lib/hooks/use-resource"
import type { Task } from "@/lib/types"
import { cn } from "@/lib/utils"

import { StatusChartSection } from "./status-chart-section"
import { SuggestActions } from "./suggest-actions"
import { TaskDetailDialog } from "./task-detail"
import { TaskForm } from "./task-form"
import {
  statusBadgeVariant,
  statusLabel,
  statusOptions,
  toTaskPayload,
  type TaskFormValues,
} from "./task-meta"
import { useEstateId } from "./use-estate-id"

const selectClass =
  "flex h-9 w-full min-w-0 rounded-md border border-input bg-background px-3 py-1 text-base shadow-sm transition-colors md:text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"

const columns: DataTableColumn<Task>[] = [
  {
    key: "title",
    header: "Title",
    value: (row) => row.title,
    render: (row) => (
      <span className="inline-flex flex-wrap items-center gap-2">
        {row.title}
        {row.executor_private ? (
          <Badge variant="outline">Private</Badge>
        ) : null}
      </span>
    ),
  },
  {
    key: "status",
    header: "Status",
    value: (row) => statusLabel(row.status),
    kind: "badge",
    badgeVariant: (row) => statusBadgeVariant(row.status),
  },
  { key: "priority", header: "Priority", value: (row) => row.priority },
  {
    key: "assignees",
    header: "Assignees",
    value: (row) => row.assignees.join(", "),
  },
  {
    key: "due_date",
    header: "Due date",
    value: (row) => row.due_date,
    kind: "date",
  },
  {
    key: "blocked",
    header: "Blocked",
    value: (row) => (row.blocked_by.length > 0 ? "Blocked" : null),
    render: (row) =>
      row.blocked_by.length > 0 ? (
        <Badge variant="destructive">Blocked</Badge>
      ) : (
        <span aria-hidden="true">&ndash;</span>
      ),
  },
]

export default function TasksPage() {
  const { role } = useMe()
  const writer = canWrite(role)
  const estateId = useEstateId()

  const { data, isPending } = useResourceList<Task>("/tasks")
  const create = useCreateResource<Task>("/tasks")
  const update = useUpdateResource<Task>("/tasks")
  const archive = useArchiveResource<Task>("/tasks")

  const [statusFilter, setStatusFilter] = React.useState("")
  const [dueBefore, setDueBefore] = React.useState("")
  const [createOpen, setCreateOpen] = React.useState(false)
  const [editOpen, setEditOpen] = React.useState(false)
  const [archiveOpen, setArchiveOpen] = React.useState(false)
  const [selectedId, setSelectedId] = React.useState<string | null>(null)

  const statusFilterId = React.useId()
  const dueBeforeId = React.useId()

  const tasks = React.useMemo(() => data ?? [], [data])
  const selected = tasks.find((task) => task.id === selectedId)

  const rows = tasks.filter((task) => {
    if (statusFilter && (task.status ?? "") !== statusFilter) return false
    if (dueBefore && !(task.due_date && task.due_date < dueBefore))
      return false
    return true
  })

  async function handleCreate(values: TaskFormValues) {
    if (!estateId) {
      throw new ApiError(
        0,
        "The estate details are still loading. Please try again in a moment.",
      )
    }
    await create.mutateAsync({
      estate_id: estateId,
      status: "todo",
      ...toTaskPayload(values),
    })
    setCreateOpen(false)
  }

  async function handleEdit(values: TaskFormValues) {
    if (!selected) return
    await update.mutateAsync({
      id: selected.id,
      data: toTaskPayload(values),
    })
    setEditOpen(false)
  }

  async function handleArchive(reason: string) {
    if (!selected) return
    await archive.mutateAsync({ id: selected.id, reason })
    setSelectedId(null)
  }

  return (
    <section aria-label="Tasks">
      <PageHeader
        title="Tasks"
        description="Everything to be done for the estate, with dependencies, checklists and comments."
        actionLabel="Add task"
        onAction={() => setCreateOpen(true)}
      />

      <SuggestActions />
      <StatusChartSection tasks={tasks} />

      <div className="mb-4 flex flex-wrap items-end gap-4">
        <div className="space-y-1.5">
          <label
            htmlFor={statusFilterId}
            className="text-sm font-medium"
          >
            Status
          </label>
          <select
            id={statusFilterId}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className={cn(selectClass, "w-44")}
          >
            <option value="">All statuses</option>
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label htmlFor={dueBeforeId} className="text-sm font-medium">
            Due before
          </label>
          <Input
            id={dueBeforeId}
            type="date"
            value={dueBefore}
            onChange={(event) => setDueBefore(event.target.value)}
            className="w-44"
          />
        </div>
      </div>

      <DataTable
        columns={columns}
        rows={rows}
        rowKey={(row) => row.id}
        isLoading={isPending}
        label="Tasks"
        filterLabel="Filter tasks"
        emptyTitle="No tasks recorded yet."
        emptyMessage="Tasks will appear here as they are added."
        onRowClick={(row) => setSelectedId(row.id)}
      />

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Add task</DialogTitle>
            <DialogDescription>
              A new action for the estate to-do list.
            </DialogDescription>
          </DialogHeader>
          <TaskForm
            allTasks={tasks}
            onSubmit={handleCreate}
            onCancel={() => setCreateOpen(false)}
          />
        </DialogContent>
      </Dialog>

      {selected ? (
        <>
          <TaskDetailDialog
            task={selected}
            allTasks={tasks}
            open={!editOpen && !archiveOpen}
            onOpenChange={(open) => {
              if (!open) setSelectedId(null)
            }}
            canWrite={writer}
            onEdit={() => setEditOpen(true)}
            onArchive={() => setArchiveOpen(true)}
          />

          <Dialog open={editOpen} onOpenChange={setEditOpen}>
            <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-lg">
              <DialogHeader>
                <DialogTitle>Edit {selected.title}</DialogTitle>
                <DialogDescription>
                  Changes are saved to the task record.
                </DialogDescription>
              </DialogHeader>
              <TaskForm
                task={selected}
                allTasks={tasks}
                onSubmit={handleEdit}
                onCancel={() => setEditOpen(false)}
              />
            </DialogContent>
          </Dialog>

          <ArchiveDialog
            open={archiveOpen}
            onOpenChange={setArchiveOpen}
            itemLabel="task"
            onConfirm={handleArchive}
          />
        </>
      ) : null}
    </section>
  )
}
