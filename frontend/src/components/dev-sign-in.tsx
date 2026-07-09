/*
  Development sign-in screen. Shown only when the dev build cannot
  identify the user (GET /me returns 401/403). It stores the chosen email
  in localStorage for the X-Dev-User shim and reloads.

  This screen never appears in production: there the identity comes from
  Cloudflare Access before the app is even reached, so /me succeeds or
  the request never arrives.
*/

import * as React from "react"

import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { DEV_USER_STORAGE_KEY } from "@/lib/api"

export function DevSignIn() {
  const [email, setEmail] = React.useState(
    () => localStorage.getItem(DEV_USER_STORAGE_KEY) ?? "",
  )

  function signIn(event: React.FormEvent) {
    event.preventDefault()
    const value = email.trim().toLowerCase()
    if (!value) return
    localStorage.setItem(DEV_USER_STORAGE_KEY, value)
    window.location.reload()
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Sign in to AD Assistant</CardTitle>
          <CardDescription>
            Development sign-in. Enter the email address you have been given
            access with; in the live version this screen is replaced by a
            one-time PIN sent to your email.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={signIn} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="dev-email" className="text-sm font-medium">
                Email address
              </label>
              <Input
                id="dev-email"
                type="email"
                autoComplete="email"
                autoFocus
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="you@example.com"
              />
            </div>
            <Button type="submit" className="w-full">
              Sign in
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  )
}
