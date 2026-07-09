import { useEffect, useId, useRef, useState } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Bell, Menu } from "lucide-react"
import { NavLink, Outlet, useNavigate } from "react-router-dom"

import { navGroups } from "@/components/layout/nav-items"
import { formatDate, humaniseCode } from "@/components/shared/formatters"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { api } from "@/lib/api"
import { canWrite, useMe } from "@/lib/auth"

import { DevSignIn } from "@/components/dev-sign-in"
import {
  NOTIFICATIONS_PATH,
  useNotifications,
} from "@/lib/hooks/use-notifications"
import { cn } from "@/lib/utils"
import type { Notification } from "@/lib/types"

function SkipLink() {
  return (
    <a
      href="#main-content"
      className="sr-only z-50 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground focus:not-sr-only focus:absolute focus:left-4 focus:top-4"
    >
      Skip to content
    </a>
  )
}

function SidebarNav() {
  return (
    <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 py-4">
      {navGroups.map((group) => (
        <div key={group.label} className="mb-6">
          <h2 className="mb-2 px-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {group.label}
          </h2>
          <ul className="space-y-1">
            {group.items.map((item) => (
              <li key={item.to}>
                <NavLink
                  to={item.to}
                  end={item.to === "/"}
                  className={({ isActive }) =>
                    cn(
                      "flex min-h-9 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                      isActive
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-foreground/80 hover:bg-accent/60 hover:text-foreground",
                    )
                  }
                >
                  <item.icon aria-hidden="true" className="size-4 shrink-0" />
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}

function MobileNav() {
  const navigate = useNavigate()

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="outline"
          size="icon"
          className="md:hidden"
          aria-label="Open navigation menu"
        >
          <Menu aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-[70vh] w-64">
        {navGroups.map((group, index) => (
          <div key={group.label}>
            {index > 0 ? <DropdownMenuSeparator /> : null}
            <DropdownMenuLabel className="text-xs uppercase tracking-wider text-muted-foreground">
              {group.label}
            </DropdownMenuLabel>
            {group.items.map((item) => (
              <DropdownMenuItem
                key={item.to}
                onSelect={() => navigate(item.to)}
              >
                <item.icon aria-hidden="true" />
                {item.label}
              </DropdownMenuItem>
            ))}
          </div>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function NotificationBell() {
  const { notifications, unreadCount, isLoading, isError, isUnavailable } =
    useNotifications()
  const { role } = useMe()
  const writer = canWrite(role)
  const queryClient = useQueryClient()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)
  const panelId = useId()

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: [NOTIFICATIONS_PATH] })

  const markRead = useMutation({
    mutationFn: (id: string) =>
      api.post<Notification>(`${NOTIFICATIONS_PATH}/${id}/read`),
    onSuccess: invalidate,
  })
  const markAllRead = useMutation({
    mutationFn: () =>
      api.post<{ marked_read: number }>(`${NOTIFICATIONS_PATH}/read-all`),
    onSuccess: invalidate,
  })

  useEffect(() => {
    if (!open) return
    function onMouseDown(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false)
    }
    document.addEventListener("mousedown", onMouseDown)
    document.addEventListener("keydown", onKeyDown)
    return () => {
      document.removeEventListener("mousedown", onMouseDown)
      document.removeEventListener("keydown", onKeyDown)
    }
  }, [open])

  const recent = notifications.slice(0, 8)
  const bellLabel =
    unreadCount > 0
      ? `Notifications (${unreadCount} unread)`
      : "Notifications"

  return (
    <div ref={containerRef} className="relative">
      <Button
        type="button"
        variant="outline"
        size="icon"
        className="relative"
        aria-label={bellLabel}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((current) => !current)}
      >
        <Bell aria-hidden="true" />
        {unreadCount > 0 ? (
          <span
            aria-hidden="true"
            className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-medium leading-none text-primary-foreground"
          >
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : null}
      </Button>

      {open ? (
        <section
          id={panelId}
          aria-label="Notifications"
          className="absolute right-0 top-full z-50 mt-2 w-80 rounded-md border bg-popover p-2 text-popover-foreground shadow-md"
        >
          <div className="flex items-center justify-between gap-2 px-2 py-1.5">
            <h2 className="text-sm font-medium">Notifications</h2>
            {writer && unreadCount > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => markAllRead.mutate()}
                disabled={markAllRead.isPending}
              >
                Mark all read
              </Button>
            ) : null}
          </div>

          {isLoading ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              Checking for notifications
            </p>
          ) : isError || isUnavailable ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              Notifications are not available yet.
            </p>
          ) : recent.length === 0 ? (
            <p className="px-2 py-3 text-sm text-muted-foreground">
              No notifications yet. You are up to date.
            </p>
          ) : (
            <ul className="max-h-80 overflow-y-auto">
              {recent.map((notification) => {
                const unread = !notification.read_at
                const body = (
                  <>
                    <span className={cn("block", unread && "font-medium")}>
                      {notification.message}
                    </span>
                    <span className="mt-0.5 block text-xs text-muted-foreground">
                      {humaniseCode(notification.event_type)}
                      {notification.created_at
                        ? ` · ${formatDate(notification.created_at)}`
                        : null}
                      {unread ? " · Unread" : null}
                    </span>
                  </>
                )
                return (
                  <li key={notification.id} className="border-t first:border-t-0">
                    {writer && unread ? (
                      <button
                        type="button"
                        onClick={() => markRead.mutate(notification.id)}
                        disabled={markRead.isPending}
                        className="w-full rounded-sm px-2 py-2 text-left text-sm hover:bg-accent/60 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring disabled:opacity-50"
                      >
                        {body}
                      </button>
                    ) : (
                      <div className="px-2 py-2 text-sm">{body}</div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
        </section>
      ) : null}
    </div>
  )
}

function UserSummary() {
  const { email, role, isLoading } = useMe()

  if (isLoading) {
    return (
      <p className="text-sm text-muted-foreground" aria-live="polite">
        Checking who is signed in
      </p>
    )
  }

  if (!email) {
    return <p className="text-sm text-muted-foreground">Not signed in</p>
  }

  return (
    <div className="flex items-center gap-2">
      <span className="max-w-48 truncate text-sm text-muted-foreground">
        {email}
      </span>
      {role ? (
        <Badge variant={canWrite(role) ? "secondary" : "outline"}>
          {role === "viewer" ? "Read only" : role}
        </Badge>
      ) : null}
    </div>
  )
}

export function AppLayout() {
  const { email, isLoading, error } = useMe()

  /* Dev builds show a sign-in screen instead of an anonymous shell when
     the backend cannot identify the user. Production identity comes from
     Cloudflare Access, so this branch never renders there. */
  if (
    import.meta.env.DEV &&
    !isLoading &&
    !email &&
    error !== null
  ) {
    return <DevSignIn />
  }

  return (
    <div className="min-h-screen md:grid md:grid-cols-[16rem_1fr]">
      <SkipLink />

      <aside className="hidden border-r bg-card md:flex md:flex-col">
        <div className="flex h-16 items-center border-b px-6">
          <span className="text-lg font-semibold tracking-tight">
            AD Assistant
          </span>
        </div>
        <SidebarNav />
        <div className="border-t px-6 py-4 text-xs text-muted-foreground">
          Estate administration and inheritance tax, in one calm place.
        </div>
      </aside>

      <div className="flex min-h-screen flex-col">
        <header className="flex h-16 items-center justify-between gap-4 border-b bg-card px-4 md:px-8">
          <div className="flex items-center gap-3">
            <MobileNav />
            <span className="text-lg font-semibold tracking-tight md:hidden">
              AD Assistant
            </span>
          </div>
          <div className="flex items-center gap-3">
            <NotificationBell />
            <UserSummary />
          </div>
        </header>

        <main id="main-content" tabIndex={-1} className="flex-1 px-4 py-8 md:px-8">
          <div className="mx-auto w-full max-w-5xl">
            <Outlet />
          </div>
        </main>

        <footer className="border-t px-4 py-4 text-xs text-muted-foreground md:px-8">
          This tool informs and drafts. It does not give legal or tax advice,
          and nothing is filed or sent automatically.
        </footer>
      </div>
    </div>
  )
}
