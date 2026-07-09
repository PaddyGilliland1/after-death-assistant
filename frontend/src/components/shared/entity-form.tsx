/*
  Schema-driven create and edit form built on react-hook-form and zod.

  Field primitives: text, textarea, money, date, select (from an enum or
  option list) and checkbox. The zod helpers in form-schema.ts (zText,
  zMoney, zDate, zEnumField, zCheckbox and their optional variants) pair
  with the field kinds so module builders declare a schema plus a field
  list and get validation, pending state and server error surfacing free.

  Money is entered in pounds as a decimal string, matching the API which
  serialises Decimal as string. Validation is client-side convenience only;
  the server remains the authority.
*/

import * as React from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  useForm,
  type DefaultValues,
  type FieldValues,
  type Path,
  type Resolver,
} from "react-hook-form"
import { z } from "zod"

import type { SelectOption } from "@/components/shared/form-schema"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { isApiError } from "@/lib/api"
import { cn } from "@/lib/utils"

export type { SelectOption }

/* ------------------------------------------------------------ field defs */

export type EntityFieldKind =
  | "text"
  | "textarea"
  | "money"
  | "date"
  | "select"
  | "checkbox"

export interface EntityField<TValues extends FieldValues> {
  name: Path<TValues>
  label: string
  kind: EntityFieldKind
  /** Options when kind is "select". */
  options?: SelectOption[]
  /** Supporting copy under the control. */
  description?: string
  placeholder?: string
  /** Adds "(optional)" to the label when false. Defaults to true. */
  required?: boolean
  autoComplete?: string
}

/* ---------------------------------------------------------------- form */

export interface EntityFormProps<TValues extends FieldValues> {
  /** Zod schema validating the form values. */
  schema: z.ZodType<TValues, FieldValues>
  /** Fields to render, in order. */
  fields: EntityField<TValues>[]
  defaultValues?: DefaultValues<TValues>
  /**
   * Called with validated values. Throw (or reject) to surface a server
   * error; ApiError messages are shown as-is.
   */
  onSubmit: (values: TValues) => Promise<void> | void
  submitLabel?: string
  /** Renders a secondary cancel button when provided. */
  onCancel?: () => void
  cancelLabel?: string
}

const controlClass =
  "flex w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-1 text-base shadow-sm transition-colors placeholder:text-muted-foreground disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 md:text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring aria-invalid:border-destructive"

export function EntityForm<TValues extends FieldValues>({
  schema,
  fields,
  defaultValues,
  onSubmit,
  submitLabel = "Save",
  onCancel,
  cancelLabel = "Cancel",
}: EntityFormProps<TValues>) {
  const [serverError, setServerError] = React.useState<string | null>(null)
  const formId = React.useId()

  const form = useForm<TValues>({
    resolver: zodResolver(schema) as Resolver<TValues>,
    defaultValues,
  })

  const { errors, isSubmitting } = form.formState

  async function handleValidSubmit(values: TValues) {
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

  function renderControl(field: EntityField<TValues>) {
    const id = `${formId}-${field.name}`
    const error = errors[field.name]
    const errorId = `${id}-error`
    const descriptionId = `${id}-description`
    const describedBy =
      [
        error ? errorId : null,
        field.description ? descriptionId : null,
      ]
        .filter(Boolean)
        .join(" ") || undefined

    const shared = {
      id,
      "aria-invalid": error ? true : undefined,
      "aria-describedby": describedBy,
      disabled: isSubmitting,
    }

    switch (field.kind) {
      case "textarea":
        return (
          <textarea
            {...shared}
            {...form.register(field.name)}
            rows={4}
            placeholder={field.placeholder}
            className={cn(controlClass, "min-h-20 py-2")}
          />
        )
      case "select":
        return (
          <select
            {...shared}
            {...form.register(field.name)}
            className={cn(controlClass, "h-9 bg-background")}
          >
            <option value="">
              {field.placeholder ?? "Choose an option"}
            </option>
            {(field.options ?? []).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        )
      case "checkbox":
        return (
          <input
            {...shared}
            {...form.register(field.name)}
            type="checkbox"
            className="size-4 rounded border-input accent-primary focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
          />
        )
      case "money":
        return (
          <Input
            {...shared}
            {...form.register(field.name)}
            type="text"
            inputMode="decimal"
            placeholder={field.placeholder ?? "0.00"}
            autoComplete={field.autoComplete ?? "off"}
          />
        )
      case "date":
        return (
          <Input
            {...shared}
            {...form.register(field.name)}
            type="date"
            autoComplete={field.autoComplete ?? "off"}
          />
        )
      default:
        return (
          <Input
            {...shared}
            {...form.register(field.name)}
            type="text"
            placeholder={field.placeholder}
            autoComplete={field.autoComplete}
          />
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

      {fields.map((field) => {
        const id = `${formId}-${field.name}`
        const error = errors[field.name]
        const isCheckbox = field.kind === "checkbox"

        return (
          <div key={field.name} className="space-y-1.5">
            <div
              className={cn(
                isCheckbox && "flex flex-row-reverse items-center justify-end gap-2",
              )}
            >
              <label htmlFor={id} className="text-sm font-medium">
                {field.label}
                {field.required === false ? (
                  <span className="font-normal text-muted-foreground">
                    {" "}
                    (optional)
                  </span>
                ) : null}
                {field.kind === "money" ? (
                  <span className="font-normal text-muted-foreground">
                    {" "}
                    (£)
                  </span>
                ) : null}
              </label>
              {isCheckbox ? renderControl(field) : null}
            </div>
            {!isCheckbox ? renderControl(field) : null}
            {field.description ? (
              <p
                id={`${id}-description`}
                className="text-xs text-muted-foreground"
              >
                {field.description}
              </p>
            ) : null}
            {error ? (
              <p id={`${id}-error`} className="text-sm text-destructive">
                {String(error.message ?? "Please check this field")}
              </p>
            ) : null}
          </div>
        )
      })}

      <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        {onCancel ? (
          <Button
            type="button"
            variant="outline"
            onClick={onCancel}
            disabled={isSubmitting}
          >
            {cancelLabel}
          </Button>
        ) : null}
        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? "Saving" : submitLabel}
        </Button>
      </div>
    </form>
  )
}
