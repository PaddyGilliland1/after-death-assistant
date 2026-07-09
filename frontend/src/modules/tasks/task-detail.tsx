/*
  Task detail dialog: full fields, a status select that PATCHes on change
  (surfacing the backend's 409 blocking-list message when a blocked task
  is moved to done), the checklist, and the comments thread with an add
  form for writers.
*/

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import { formatDate } from "@/components/shared/formatters"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { api, isApiError } from "@/lib/api"
import { useUpdateResource } from "@/lib/hooks/use-resource"
import type { Task } from "@/lib/types"
import { cn } from "@/lib/utils"

import {
  blockedTaskError,
  blockingTitles,
  commentsKey,
  statusLabel,
  statusOptions,
  type TaskComment,
} from "./task-meta"

const controlClass =
  "flex w-full min-w-0 rounded-md border border-input bg-background px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"

function DetailRow({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="grid grid-cols-[10rem_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd>{children ?? <span aria-hidden="true">&ndash;</span>}</dd>
    </div>
  )
}

function CommentsThread({
  taskId,
  canWrite,
}: {
  taskId: string
  canWrite: boolean
}) {
  const queryClient = useQueryClient()
  const [body, setBody] = React.useState("")
  const [error, setError] = React.useState<string | null>(null)
  const bodyId = React.useId()

  const { data, isPending } = useQuery({
    queryKey: commentsKey(taskId),
    queryFn: async () => {
      try {
        return await api.get<TaskComment[]>(`/tasks/${taskId}/comments`)
      } catch (cause) {
        if (isApiError(cause) && cause.status === 404) return null
        throw cause
      }
    },
  })

  const create = useMutation({
    mutationFn: (input: { body: string }) =>
      api.post<TaskComment>(`/tasks/${taskId}/comments`, input),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: commentsKey(taskId) }),
  })

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setError(null)
    if (!body.trim()) {
      setError("Please write a comment before posting.")
      return
    }
    try {
      await create.mutateAsync({ body: body.trim() })
      setBody("")
    } catch (cause) {
      setError(
        isApiError(cause)
          ? cause.message
          : "Something went wrong while saving. Please try again.",
      )
    }
  }

  const comments = data ?? []

  return (
    <section aria-label="Comments" className="space-y-3">
      <h3 className="text-sm font-semibold">Comments</h3>
      {isPending ? (
        <p className="text-sm text-muted-foreground">Loading comments</p>
      ) : comments.length === 0 ? (
        <p className="text-sm text-muted-foreground">No comments yet.</p>
      ) : (
        <ol className="space-y-3">
          {comments.map((comment) => (
            <li
              key={comment.id}
              className="border-b pb-3 text-sm last:border-b-0 last:pb-0"
            >
              <p>{comment.body}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {comment.created_by} · {formatDate(comment.created_at)}
              </p>
            </li>
          ))}
        </ol>
      )}
      {canWrite ? (
        <form onSubmit={handleSubmit} noValidate className="space-y-2">
          <label htmlFor={bodyId} className="text-sm font-medium">
            Add a comment
          </label>
          <textarea
            id={bodyId}
            value={body}
            onChange={(event) => setBody(event.target.value)}
            rows={2}
            disabled={create.isPending}
            className={cn(controlClass, "min-h-16 py-2")}
          />
          {error ? (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          ) : null}
          <Button type="submit" size="sm" disabled={create.isPending}>
            {create.isPending ? "Posting" : "Post comment"}
          </Button>
        </form>
      ) : null}
    </section>
  )
}

export interface TaskDetailDialogProps {
  task: Task
  /** All tasks, used to resolve blocking task titles. */
  allTasks: Task[]
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Whether the current role can create or change records. */
  canWrite: boolean
  onEdit: () => void
  onArchive: () => void
}

export function TaskDetailDialog({
  task,
  allTasks,
  open,
  onOpenChange,
  canWrite,
  onEdit,
  onArchive,
}: TaskDetailDialogProps) {
  const update = useUpdateResource<Task>("/tasks")
  const [statusError, setStatusError] = React.useState<string | null>(null)
  const statusId = React.useId()

  async function handleStatusChange(next: string) {
    setStatusError(null)
    try {
      await update.mutateAsync({
        id: task.id,
        data: { status: next || null },
      })
    } catch (error) {
      const blocked = blockedTaskError(error)
      if (blocked) {
        const titles = blockingTitles(blocked.blocking, allTasks)
        setStatusError(
          titles.length > 0
            ? `${blocked.message} Blocking tasks: ${titles.join(", ")}.`
            : blocked.message,
        )
      } else {
        setStatusError(
          isApiError(error)
            ? error.message
            : "Something went wrong while saving. Please try again.",
        )
      }
    }
  }

  const blockers = blockingTitles(task.blocked_by, allTasks)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex flex-wrap items-center gap-2">
            {task.title}
            {task.blocked_by.length > 0 ? (
              <Badge variant="destructive">Blocked</Badge>
            ) : null}
            {task.executor_private ? (
              <Badge variant="outline">Private</Badge>
            ) : null}
          </DialogTitle>
          <DialogDescription>
            {task.description || "No description recorded."}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-1.5">
          <label htmlFor={statusId} className="text-sm font-medium">
            Status
          </label>
          {canWrite ? (
            <select
              id={statusId}
              value={task.status ?? ""}
              onChange={(event) => handleStatusChange(event.target.value)}
              disabled={update.isPending}
              className={cn(controlClass, "h-9 max-w-56")}
            >
              <option value="">No status</option>
              {statusOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : (
            <p id={statusId} className="text-sm">
              {statusLabel(task.status)}
            </p>
          )}
          {statusError ? (
            <p role="alert" className="text-sm text-destructive">
              {statusError}
            </p>
          ) : null}
        </div>

        <dl className="divide-y">
          <DetailRow label="Priority">
            {task.priority ?? <span aria-hidden="true">&ndash;</span>}
          </DetailRow>
          <DetailRow label="Assignees">
            {task.assignees.length > 0 ? (
              task.assignees.join(", ")
            ) : (
              <span aria-hidden="true">&ndash;</span>
            )}
          </DetailRow>
          <DetailRow label="Start date">
            {task.start_date ? (
              formatDate(task.start_date)
            ) : (
              <span aria-hidden="true">&ndash;</span>
            )}
          </DetailRow>
          <DetailRow label="Due date">
            {task.due_date ? (
              formatDate(task.due_date)
            ) : (
              <span aria-hidden="true">&ndash;</span>
            )}
          </DetailRow>
          <DetailRow label="Blocked by">
            {blockers.length > 0 ? (
              blockers.join(", ")
            ) : (
              <span aria-hidden="true">&ndash;</span>
            )}
          </DetailRow>
        </dl>

        {task.checklist.length > 0 ? (
          <section aria-label="Checklist" className="space-y-2">
            <h3 className="text-sm font-semibold">Checklist</h3>
            <ul className="space-y-1">
              {task.checklist.map((item, index) => (
                <li key={index} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={item.done}
                    disabled
                    aria-label={`${item.text} ${item.done ? "done" : "not done"}`}
                    className="size-4 rounded border-input accent-primary"
                  />
                  <span
                    className={cn(item.done && "text-muted-foreground")}
                  >
                    {item.text}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <CommentsThread taskId={task.id} canWrite={canWrite} />

        <DialogFooter className="gap-2">
          {canWrite ? (
            <>
              <Button type="button" variant="outline" onClick={onEdit}>
                Edit
              </Button>
              <Button type="button" variant="destructive" onClick={onArchive}>
                Archive
              </Button>
            </>
          ) : null}
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
          >
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
