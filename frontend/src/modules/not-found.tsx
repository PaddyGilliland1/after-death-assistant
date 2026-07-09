import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"

export default function NotFoundPage() {
  return (
    <section aria-label="Page not found" className="py-16 text-center">
      <h1 className="text-2xl font-semibold tracking-tight">Page not found</h1>
      <p className="mt-2 text-muted-foreground">
        That page does not exist. Nothing has been lost.
      </p>
      <Button asChild className="mt-6">
        <Link to="/">Go to the dashboard</Link>
      </Button>
    </section>
  )
}
