/*
  Task module constants, form schema, payload mapping and the helper that
  surfaces the backend's 409 "blocked task" response. Field names mirror
  backend/app/schemas/tasks_costs.py (TaskCreate/TaskUpdate), which remains
  authoritative.
*/

import { z } from "zod"

import {
  zOptionalDate,
  zOptionalText,
  zText,
  type SelectOption,
} from "@/components/shared/form-schema"
import { isApiError } from "@/lib/api"
import type { Task } from "@/lib/types"

export const statusOptions: SelectOption[] = [
  { value: "todo", label: "To do" },
  { value: "in_progress", label: "In progress" },
  { value: "done", label: "Done" },
]

export const priorityOptions: SelectOption[] = [
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
  { value: "urgent", label: "Urgent" },
]

/** Human readable label for a status value. */
export function statusLabel(status: string | null): string {
  if (!status) return "No status"
  return (
    statusOptions.find((option) => option.value === status)?.label ?? status
  )
}

export function statusBadgeVariant(
  status: string | null,
): "default" | "secondary" | "outline" {
  if (status === "done") return "default"
  if (status === "in_progress") return "secondary"
  return "outline"
}

/** Comments on a task, from GET /tasks/{id}/comments (tasks_costs.py). */
export interface TaskComment {
  id: string
  estate_id: string
  task_id: string
  body: string
  created_at: string
  updated_at: string
  created_by: string
}

export const commentsKey = (taskId: string) =>
  ["/tasks", "comments", taskId] as const

/* ----------------------------------------------------------------- form */

export const taskFormSchema = z.object({
  title: zText("Enter a title for the task"),
  description: zOptionalText(),
  priority: zOptionalText(),
  start_date: zOptionalDate(),
  due_date: zOptionalDate(),
  assignees: zOptionalText(),
  blocked_by: z.array(z.string()),
  checklist: z.array(z.object({ text: z.string(), done: z.boolean() })),
  executor_private: z.boolean(),
})

export type TaskFormValues = z.infer<typeof taskFormSchema>

/** Default form values, from an existing task when editing. */
export function taskFormDefaults(task?: Task): TaskFormValues {
  return {
    title: task?.title ?? "",
    description: task?.description ?? "",
    priority: task?.priority ?? "",
    start_date: task?.start_date ?? "",
    due_date: task?.due_date ?? "",
    assignees: task?.assignees?.join(", ") ?? "",
    blocked_by: task?.blocked_by ?? [],
    checklist: task?.checklist?.map((item) => ({ ...item })) ?? [],
    executor_private: task?.executor_private ?? false,
  }
}

/** Maps validated form values to the TaskCreate/TaskUpdate shape. */
export function toTaskPayload(values: TaskFormValues) {
  return {
    title: values.title,
    description: values.description || null,
    priority: values.priority || null,
    start_date: values.start_date || null,
    due_date: values.due_date || null,
    assignees: values.assignees
      .split(",")
      .map((email) => email.trim())
      .filter(Boolean),
    blocked_by: values.blocked_by,
    checklist: values.checklist
      .map((item) => ({ text: item.text.trim(), done: item.done }))
      .filter((item) => item.text.length > 0),
    executor_private: values.executor_private,
  }
}

/* -------------------------------------------------------- blocked (409) */

export interface BlockedTaskError {
  message: string
  blocking: string[]
}

/**
 * Extracts the backend's 409 blocking response, which arrives as
 * { detail: { message, blocking: [task ids] } }. Returns null for any
 * other error so callers can fall back to a generic message.
 */
export function blockedTaskError(error: unknown): BlockedTaskError | null {
  if (!isApiError(error) || error.status !== 409) return null
  const body = error.detail
  if (body && typeof body === "object") {
    const detail = (body as Record<string, unknown>).detail
    if (detail && typeof detail === "object") {
      const record = detail as Record<string, unknown>
      const message =
        typeof record.message === "string" ? record.message : error.message
      const blocking = Array.isArray(record.blocking)
        ? record.blocking.map(String)
        : []
      return { message, blocking }
    }
  }
  return { message: error.message, blocking: [] }
}

/** Titles for blocking task ids, falling back to the id itself. */
export function blockingTitles(ids: string[], tasks: Task[]): string[] {
  return ids.map(
    (id) => tasks.find((task) => task.id === id)?.title ?? id,
  )
}
