/*
  Notifications polling. GET /notifications every 60 seconds, with the
  unread count derived from rows that have no read_at timestamp. A 404
  (endpoint not built yet) resolves to "unavailable" rather than an error.
*/

import { useQuery } from "@tanstack/react-query"

import { api, isApiError } from "@/lib/api"
import type { Notification } from "@/lib/types"

export const NOTIFICATIONS_PATH = "/notifications"
export const NOTIFICATIONS_POLL_INTERVAL_MS = 60_000

export function useNotifications(options?: { refetchInterval?: number }) {
  const query = useQuery<Notification[] | null>({
    queryKey: [NOTIFICATIONS_PATH, "list"],
    queryFn: async () => {
      try {
        return await api.get<Notification[]>(NOTIFICATIONS_PATH)
      } catch (error) {
        if (isApiError(error) && error.status === 404) return null
        throw error
      }
    },
    refetchInterval:
      options?.refetchInterval ?? NOTIFICATIONS_POLL_INTERVAL_MS,
    retry: (failureCount, error) => {
      if (isApiError(error) && error.status === 404) return false
      return failureCount < 2
    },
  })

  const notifications = query.data ?? []
  const unread = notifications.filter((item) => !item.read_at)

  return {
    /** All notifications for the signed-in user, newest first from the API. */
    notifications,
    /** Notifications not yet read. */
    unread,
    /** Number of unread notifications, for badges. */
    unreadCount: unread.length,
    /** True while the first fetch is in flight. */
    isLoading: query.isPending,
    /** True when the request failed (server unreachable or errored). */
    isError: query.isError,
    /** True when the endpoint is not available yet (404). */
    isUnavailable: !query.isPending && !query.isError && query.data === null,
  }
}
