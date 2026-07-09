/*
  Authentication helpers.

  Roles are enforced server side. The helpers here only decide which
  affordances the UI shows: hiding a button for a viewer is a courtesy,
  never a security control.
*/

import { useQuery } from "@tanstack/react-query"

import { api } from "@/lib/api"

export type Role = "executor" | "admin" | "viewer"

export interface Me {
  email: string
  role: Role
}

/**
 * True when the role may create or change records (executor or admin).
 * Viewers are read only. The server remains the authority on every write.
 */
export function canWrite(role: Role | null | undefined): boolean {
  return role === "executor" || role === "admin"
}

/** Fetches the signed-in user from GET /me. */
export function useMe() {
  const query = useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/me"),
    staleTime: 5 * 60 * 1000,
    retry: 1,
  })

  return {
    me: query.data ?? null,
    email: query.data?.email ?? null,
    role: query.data?.role ?? null,
    isLoading: query.isLoading,
    error: query.error,
  }
}
