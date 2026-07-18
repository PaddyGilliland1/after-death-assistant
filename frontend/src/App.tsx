import { lazy, Suspense } from "react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { BrowserRouter, Route, Routes } from "react-router-dom"

import { ErrorBoundary } from "@/components/error-boundary"
import { AppLayout } from "@/components/layout/app-layout"
import { Toaster } from "@/components/ui/sonner"

const DashboardPage = lazy(() => import("@/modules/dashboard"))
const TasksPage = lazy(() => import("@/modules/tasks"))
const AssetsPage = lazy(() => import("@/modules/assets"))
const DebtorsCreditorsPage = lazy(() => import("@/modules/debtors_creditors"))
const ContactsPage = lazy(() => import("@/modules/contacts"))
const CostsPage = lazy(() => import("@/modules/costs"))
const AccountsPage = lazy(() => import("@/modules/accounts"))
const IhtPage = lazy(() => import("@/modules/iht"))
const KnowledgePage = lazy(() => import("@/modules/knowledge"))
const HelpPage = lazy(() => import("@/modules/help"))
const DraftsPage = lazy(() => import("@/modules/drafts"))
const DocumentsPage = lazy(() => import("@/modules/documents"))
const TimelinePage = lazy(() => import("@/modules/timeline"))
const ReliefsPage = lazy(() => import("@/modules/reliefs"))
const AdminTaxPage = lazy(() => import("@/modules/admin_tax"))
const TracingPage = lazy(() => import("@/modules/tracing"))
const DigitalPage = lazy(() => import("@/modules/digital"))
const VeteranPage = lazy(() => import("@/modules/veteran"))
const ExecutorPage = lazy(() => import("@/modules/executor"))
const AdminPage = lazy(() => import("@/modules/admin"))
const NotFoundPage = lazy(() => import("@/modules/not-found"))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,
    },
  },
})

function PageLoading() {
  return (
    <div role="status" className="py-16 text-center text-muted-foreground">
      Loading
    </div>
  )
}

export default function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <Routes>
            <Route element={<AppLayout />}>
              <Route
                index
                element={
                  <Suspense fallback={<PageLoading />}>
                    <DashboardPage />
                  </Suspense>
                }
              />
              {[
                { path: "/tasks", element: <TasksPage /> },
                { path: "/assets", element: <AssetsPage /> },
                {
                  path: "/debtors-creditors",
                  element: <DebtorsCreditorsPage />,
                },
                { path: "/contacts", element: <ContactsPage /> },
                { path: "/costs", element: <CostsPage /> },
                { path: "/accounts", element: <AccountsPage /> },
                { path: "/iht", element: <IhtPage /> },
                { path: "/knowledge", element: <KnowledgePage /> },
                { path: "/help", element: <HelpPage /> },
                { path: "/drafts", element: <DraftsPage /> },
                { path: "/documents", element: <DocumentsPage /> },
                { path: "/timeline", element: <TimelinePage /> },
                { path: "/reliefs", element: <ReliefsPage /> },
                { path: "/admin-tax", element: <AdminTaxPage /> },
                { path: "/tracing", element: <TracingPage /> },
                { path: "/digital", element: <DigitalPage /> },
                { path: "/veteran", element: <VeteranPage /> },
                { path: "/executor", element: <ExecutorPage /> },
                { path: "/admin", element: <AdminPage /> },
                { path: "*", element: <NotFoundPage /> },
              ].map(({ path, element }) => (
                <Route
                  key={path}
                  path={path}
                  element={
                    <Suspense fallback={<PageLoading />}>{element}</Suspense>
                  }
                />
              ))}
            </Route>
          </Routes>
          <Toaster />
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
