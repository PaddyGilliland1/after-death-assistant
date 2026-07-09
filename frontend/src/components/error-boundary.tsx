import * as React from "react"

import { Button } from "@/components/ui/button"
import { Card, CardContent } from "@/components/ui/card"

interface ErrorBoundaryProps {
  children: React.ReactNode
}

interface ErrorBoundaryState {
  hasError: boolean
}

/*
  Catches unexpected render errors and shows a calm recovery screen
  instead of a blank page.
*/
export class ErrorBoundary extends React.Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  state: ErrorBoundaryState = { hasError: false }

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true }
  }

  componentDidCatch(error: unknown, info: React.ErrorInfo) {
    // Log for diagnosis in development. No personal data is included.
    if (import.meta.env.DEV) {
      console.error("Unexpected error in the interface", error, info)
    }
  }

  handleReset = () => {
    this.setState({ hasError: false })
  }

  render() {
    if (this.state.hasError) {
      return (
        <main className="flex min-h-screen items-center justify-center p-6">
          <Card className="w-full max-w-md">
            <CardContent className="flex flex-col items-center gap-4 py-10 text-center">
              <h1 className="text-lg font-semibold">Something went wrong</h1>
              <p className="text-sm text-muted-foreground">
                Nothing has been lost. Please try again, and if the problem
                continues, reload the page.
              </p>
              <Button onClick={this.handleReset}>Try again</Button>
            </CardContent>
          </Card>
        </main>
      )
    }

    return this.props.children
  }
}
