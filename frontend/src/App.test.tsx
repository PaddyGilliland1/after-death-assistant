import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import App from "@/App"

describe("application shell", () => {
  it("renders the layout with accessible landmarks and navigation", async () => {
    render(<App />)

    // App name appears in the shell.
    expect(screen.getAllByText("AD Assistant").length).toBeGreaterThan(0)

    // The primary navigation landmark is present and labelled.
    const nav = await screen.findByRole("navigation", { name: "Primary" })
    expect(nav).toBeInTheDocument()

    // A skip link is the first focusable affordance.
    expect(
      screen.getByRole("link", { name: "Skip to content" }),
    ).toHaveAttribute("href", "#main-content")

    // Every module is reachable from the sidebar.
    for (const label of [
      "Dashboard",
      "Tasks",
      "Assets",
      "Debtors and creditors",
      "Contacts",
      "Costs",
      "Documents",
      "Estate accounts",
      "Inheritance tax",
      "Reliefs",
      "Administration tax",
      "Knowledge library",
      "Timeline",
      "Asset tracing",
      "Digital assets",
      "Veteran checklist",
      "Executor protection",
      "Settings and audit",
    ]) {
      expect(screen.getByRole("link", { name: label })).toBeInTheDocument()
    }

    // The main content landmark exists for the skip link target.
    expect(document.getElementById("main-content")).not.toBeNull()

    // The dashboard renders its heading once the lazy module loads.
    expect(
      await screen.findByRole("heading", { name: "Dashboard", level: 1 }),
    ).toBeInTheDocument()
  })
})
