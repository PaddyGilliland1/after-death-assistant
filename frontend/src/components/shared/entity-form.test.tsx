import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { z } from "zod"

import { ApiError } from "@/lib/api"

import { EntityForm, type EntityField } from "./entity-form"
import {
  optionsFromEnum,
  zCheckbox,
  zEnumField,
  zMoney,
  zText,
} from "./form-schema"

const schema = z.object({
  name: zText("Enter a name"),
  amount: zMoney(),
  category: zEnumField(["funeral", "probate"] as const),
  reimbursable: zCheckbox(),
})

type Values = z.infer<typeof schema>

const fields: EntityField<Values>[] = [
  { name: "name", label: "Name", kind: "text" },
  { name: "amount", label: "Amount", kind: "money" },
  {
    name: "category",
    label: "Category",
    kind: "select",
    options: optionsFromEnum(["funeral", "probate"]),
  },
  { name: "reimbursable", label: "Reimbursable", kind: "checkbox" },
]

function renderForm(onSubmit: (values: Values) => Promise<void> | void) {
  return render(
    <EntityForm<Values>
      schema={schema}
      fields={fields}
      defaultValues={{
        name: "",
        amount: "",
        category: undefined,
        reimbursable: false,
      }}
      onSubmit={onSubmit}
      submitLabel="Save cost"
    />,
  )
}

describe("EntityForm", () => {
  it("shows zod validation messages and does not submit invalid values", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    renderForm(onSubmit)

    await user.type(screen.getByLabelText(/Amount/), "not-money")
    await user.click(screen.getByRole("button", { name: "Save cost" }))

    expect(await screen.findByText("Enter a name")).toBeInTheDocument()
    expect(
      screen.getByText("Enter an amount in pounds, for example 1250 or 1250.50"),
    ).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()

    const amountInput = screen.getByLabelText(/Amount/)
    expect(amountInput).toHaveAttribute("aria-invalid", "true")
    expect(amountInput.getAttribute("aria-describedby")).toBeTruthy()
  })

  it("submits validated values", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    renderForm(onSubmit)

    await user.type(screen.getByLabelText("Name"), "Alex Example")
    await user.type(screen.getByLabelText(/Amount/), "1250.50")
    await user.selectOptions(screen.getByLabelText("Category"), "funeral")
    await user.click(screen.getByLabelText("Reimbursable"))
    await user.click(screen.getByRole("button", { name: "Save cost" }))

    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Alex Example",
      amount: "1250.50",
      category: "funeral",
      reimbursable: true,
    })
  })

  it("disables the submit button while saving", async () => {
    const user = userEvent.setup()
    let release: () => void = () => {}
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          release = resolve
        }),
    )
    renderForm(onSubmit)

    await user.type(screen.getByLabelText("Name"), "Alex Example")
    await user.type(screen.getByLabelText(/Amount/), "10")
    await user.selectOptions(screen.getByLabelText("Category"), "probate")
    await user.click(screen.getByRole("button", { name: "Save cost" }))

    expect(
      await screen.findByRole("button", { name: "Saving" }),
    ).toBeDisabled()

    release()
    expect(
      await screen.findByRole("button", { name: "Save cost" }),
    ).toBeEnabled()
  })

  it("surfaces a server error from a rejected submit", async () => {
    const user = userEvent.setup()
    const onSubmit = vi
      .fn()
      .mockRejectedValue(new ApiError(422, "The amount must be positive."))
    renderForm(onSubmit)

    await user.type(screen.getByLabelText("Name"), "Alex Example")
    await user.type(screen.getByLabelText(/Amount/), "10")
    await user.selectOptions(screen.getByLabelText("Category"), "probate")
    await user.click(screen.getByRole("button", { name: "Save cost" }))

    const alert = await screen.findByRole("alert")
    expect(alert).toHaveTextContent("The amount must be positive.")
  })
})
