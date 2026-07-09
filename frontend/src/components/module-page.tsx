import { Inbox } from "lucide-react"

import { Card, CardContent } from "@/components/ui/card"

interface ModulePageProps {
  title: string
  purpose: string
  emptyMessage?: string
}

/*
  Shared scaffold for a module index page: a heading, a one line purpose,
  and a calm empty state until the module is built out.
*/
export function ModulePage({
  title,
  purpose,
  emptyMessage = "Nothing recorded here yet.",
}: ModulePageProps) {
  return (
    <section aria-label={title}>
      <header className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 max-w-prose text-muted-foreground">{purpose}</p>
      </header>

      <Card>
        <CardContent className="flex flex-col items-center gap-3 py-16 text-center">
          <Inbox aria-hidden="true" className="size-8 text-muted-foreground" />
          <p className="font-medium">{emptyMessage}</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Records will appear here as the estate is set up. There is no need
            to do anything yet.
          </p>
        </CardContent>
      </Card>
    </section>
  )
}
