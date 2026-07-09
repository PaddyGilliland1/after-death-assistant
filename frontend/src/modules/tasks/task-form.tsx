/*
  Create and edit form for a task. Built directly on react-hook-form and
  zod (rather than the shared EntityForm) because tasks need two richer
  controls: a checklist editor (add, toggle, remove {text, done} items)
  and a dependency picker (multi-select of other tasks for blocked_by).
*/

import * as React from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { Trash2 } from "lucide-react"
import { useFieldArray, useForm, type Resolver } from "react-hook-form"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { isApiError } from "@/lib/api"
import type { Task } from "@/lib/types"
import { cn } from "@/lib/utils"

import {
  priorityOptions,
  taskFormDefaults,
  taskFormSchema,
  type TaskFormValues,
} from "./task-meta"

const controlClass =
  "flex w-full min-w-0 rounded-md border border-input bg-background px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-invalid:border-destructive"

export interface TaskFormProps {
  /** When set, the form edits this task; otherwise it creates one. */
  task?: Task
  /** Other tasks offered in the blocked-by dependency picker. */
  allTasks: Task[]
  onSubmit: (values: TaskFormValues) => Promise<void>
  onCancel: () => void
}

export function TaskForm({ task, allTasks, onSubmit, onCancel }: TaskFormProps) {
  const [serverError, setServerError] = React.useState<string | null>(null)
  const formId = React.useId()

  const form = useForm<TaskFormValues>({
    resolver: zodResolver(taskFormSchema) as Resolver<TaskFormValues>,
    defaultValues: taskFormDefaults(task),
  })
  const { errors, isSubmitting } = form.formState
  const checklist = useFieldArray({ control: form.control, name: "checklist" })
  const blockedBy = form.watch("blocked_by")

  const dependencyChoices = allTasks.filter(
    (candidate) => candidate.id !== task?.id,
  )

  function toggleBlockedBy(id: string) {
    form.setValue(
      "blocked_by",
      blockedBy.includes(id)
        ? blockedBy.filter((existing) => existing !== id)
        : [...blockedBy, id],
      { shouldDirty: true },
    )
  }

  async function handleValidSubmit(values: TaskFormValues) {
    setServerError(null)
    try {
      await onSubmit(values)
    } catch (error) {
      setServerError(
        isApiError(error)
          ? error.message
          : "Something went wrong while saving. Please try again.",
      )
    }
  }

  return (
    <form
      noValidate
      onSubmit={form.handleSubmit(handleValidSubmit)}
      className="space-y-5"
    >
      {serverError ? (
        <div
          role="alert"
          className="rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
        >
          {serverError}
        </div>
      ) : null}

      <div className="space-y-1.5">
        <label htmlFor={`${formId}-title`} className="text-sm font-medium">
          Title
        </label>
        <Input
          id={`${formId}-title`}
          type="text"
          disabled={isSubmitting}
          aria-invalid={errors.title ? true : undefined}
          aria-describedby={errors.title ? `${formId}-title-error` : undefined}
          {...form.register("title")}
        />
        {errors.title ? (
          <p id={`${formId}-title-error`} className="text-sm text-destructive">
            {errors.title.message}
          </p>
        ) : null}
      </div>

      <div className="space-y-1.5">
        <label
          htmlFor={`${formId}-description`}
          className="text-sm font-medium"
        >
          Description{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <textarea
          id={`${formId}-description`}
          rows={3}
          disabled={isSubmitting}
          className={cn(controlClass, "min-h-20 py-2")}
          {...form.register("description")}
        />
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div className="space-y-1.5">
          <label
            htmlFor={`${formId}-priority`}
            className="text-sm font-medium"
          >
            Priority{" "}
            <span className="font-normal text-muted-foreground">
              (optional)
            </span>
          </label>
          <select
            id={`${formId}-priority`}
            disabled={isSubmitting}
            className={cn(controlClass, "h-9")}
            {...form.register("priority")}
          >
            <option value="">No priority</option>
            {priorityOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor={`${formId}-start-date`}
            className="text-sm font-medium"
          >
            Start date{" "}
            <span className="font-normal text-muted-foreground">
              (optional)
            </span>
          </label>
          <Input
            id={`${formId}-start-date`}
            type="date"
            disabled={isSubmitting}
            {...form.register("start_date")}
          />
        </div>
        <div className="space-y-1.5">
          <label
            htmlFor={`${formId}-due-date`}
            className="text-sm font-medium"
          >
            Due date{" "}
            <span className="font-normal text-muted-foreground">
              (optional)
            </span>
          </label>
          <Input
            id={`${formId}-due-date`}
            type="date"
            disabled={isSubmitting}
            {...form.register("due_date")}
          />
        </div>
      </div>

      <div className="space-y-1.5">
        <label htmlFor={`${formId}-assignees`} className="text-sm font-medium">
          Assignees{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </label>
        <Input
          id={`${formId}-assignees`}
          type="text"
          disabled={isSubmitting}
          placeholder="one@example.com, two@example.com"
          aria-describedby={`${formId}-assignees-description`}
          {...form.register("assignees")}
        />
        <p
          id={`${formId}-assignees-description`}
          className="text-xs text-muted-foreground"
        >
          Email addresses, separated by commas.
        </p>
      </div>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">Checklist</legend>
        {checklist.fields.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No checklist items yet.
          </p>
        ) : (
          <ul className="space-y-2">
            {checklist.fields.map((field, index) => (
              <li key={field.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  aria-label={`Checklist item ${index + 1} done`}
                  disabled={isSubmitting}
                  className="size-4 rounded border-input accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  {...form.register(`checklist.${index}.done`)}
                />
                <Input
                  type="text"
                  aria-label={`Checklist item ${index + 1}`}
                  placeholder="Checklist item"
                  disabled={isSubmitting}
                  {...form.register(`checklist.${index}.text`)}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  aria-label={`Remove checklist item ${index + 1}`}
                  disabled={isSubmitting}
                  onClick={() => checklist.remove(index)}
                >
                  <Trash2 aria-hidden="true" className="size-4" />
                </Button>
              </li>
            ))}
          </ul>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isSubmitting}
          onClick={() => checklist.append({ text: "", done: false })}
        >
          Add checklist item
        </Button>
      </fieldset>

      <fieldset className="space-y-2">
        <legend className="text-sm font-medium">
          Blocked by{" "}
          <span className="font-normal text-muted-foreground">(optional)</span>
        </legend>
        <p className="text-xs text-muted-foreground">
          This task cannot be completed while any selected task is still open.
        </p>
        {dependencyChoices.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            There are no other tasks to depend on yet.
          </p>
        ) : (
          <ul className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2">
            {dependencyChoices.map((candidate) => {
              const id = `${formId}-blocked-${candidate.id}`
              return (
                <li key={candidate.id} className="flex items-center gap-2">
                  <input
                    id={id}
                    type="checkbox"
                    checked={blockedBy.includes(candidate.id)}
                    onChange={() => toggleBlockedBy(candidate.id)}
                    disabled={isSubmitting}
                    className="size-4 rounded border-input accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                  />
                  <label htmlFor={id} className="text-sm">
                    {candidate.title}
                  </label>
                </li>
              )
            })}
          </ul>
        )}
      </fieldset>

      <div className="flex flex-row-reverse items-center justify-end gap-2">
        <label
          htmlFor={`${formId}-executor-private`}
          className="text-sm font-medium"
        >
          Private to executors
        </label>
        <input
          id={`${formId}-executor-private`}
          type="checkbox"
          disabled={isSubmitting}
          className="size-4 rounded border-input accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          {...form.register("executor_private")}
        />
      </div>

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <Button
          type="button"
          variant="outline"
          onClick={onCancel}
          disabled={isSubmitting}
        >
          Cancel
        </Button>
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving" : task ? "Save changes" : "Add task"}
        </Button>
      </div>
    </form>
  )
}
