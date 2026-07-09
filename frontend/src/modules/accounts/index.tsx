/*
  Estate accounts (P1): the four-account trial balance from
  GET /estate/accounts rendered as calm cards, headline stat cards for
  net estate, residue and legacies total, a reconciliation status line
  driven by is_balanced, the per-beneficiary distribution table and a
  donut of residuary shares.

  Every money figure is displayed exactly as the API returned it (see
  ./money.ts); nothing on this page computes.
*/

import { CircleCheck, TriangleAlert } from "lucide-react"

import { DataTable, type DataTableColumn } from "@/components/shared/data-table"
import { PageHeader } from "@/components/shared/page-header"
import { StatCard } from "@/components/shared/stat-card"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { useResourceList } from "@/lib/hooks/use-resource"
import type { Contact } from "@/lib/types"

import { AccountsExportActions } from "./export-actions"
import { formatMoneyExact, formatShare } from "./money"
import { ShareDonut } from "./share-donut"
import {
  useEstateAccounts,
  type AccountsDistribution,
  type EstateAccounts,
} from "./use-estate-accounts"

interface FigureConfig {
  key: keyof Pick<
    EstateAccounts,
    | "net_estate"
    | "residue"
    | "legacies_total"
    | "capital_account"
    | "income_account"
    | "administration_account"
    | "distribution_account"
  >
  label: string
  description: string
}

const headlineFigures: FigureConfig[] = [
  {
    key: "net_estate",
    label: "Net estate",
    description: "The estate's share of assets less liabilities",
  },
  {
    key: "residue",
    label: "Residue",
    description: "What remains for the residuary beneficiaries",
  },
  {
    key: "legacies_total",
    label: "Legacies total",
    description: "Pecuniary and specific legacies",
  },
]

const trialBalanceFigures: FigureConfig[] = [
  {
    key: "capital_account",
    label: "Capital account",
    description: "The net estate plus gains or losses on realisation",
  },
  {
    key: "income_account",
    label: "Income account",
    description: "Income received since the date of death",
  },
  {
    key: "administration_account",
    label: "Administration account",
    description: "Administration costs and inheritance tax",
  },
  {
    key: "distribution_account",
    label: "Distribution account",
    description: "Legacies plus the residue to distribute",
  },
]

function ReconciliationLine({ isBalanced }: { isBalanced: boolean }) {
  if (isBalanced) {
    return (
      <p
        role="status"
        className="flex items-center gap-2 rounded-md border border-green-700/30 bg-green-600/10 px-4 py-3 text-sm text-green-800 dark:text-green-400"
      >
        <CircleCheck aria-hidden="true" className="size-4 shrink-0" />
        Accounts reconcile. What came into the estate equals what has been
        paid out, set aside and distributed.
      </p>
    )
  }
  return (
    <p
      role="alert"
      className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive"
    >
      <TriangleAlert aria-hidden="true" className="size-4 shrink-0" />
      Accounts do not reconcile. Check the most recent entries: a value,
      liability, cost or distribution may have been recorded incorrectly.
    </p>
  )
}

function FigureGrid({
  figures,
  accounts,
  isLoading,
  columnsClass,
}: {
  figures: FigureConfig[]
  accounts: EstateAccounts | null | undefined
  isLoading?: boolean
  columnsClass: string
}) {
  return (
    <div className={`grid gap-4 ${columnsClass}`}>
      {figures.map((figure) => (
        <StatCard
          key={figure.key}
          label={figure.label}
          description={figure.description}
          value={
            accounts ? formatMoneyExact(accounts[figure.key], "") || null : null
          }
          isLoading={isLoading}
        />
      ))}
    </div>
  )
}

function moneyCell(value: string) {
  return <span className="tabular-nums">{formatMoneyExact(value)}</span>
}

export default function AccountsPage() {
  const { data: accounts, isPending, isError } = useEstateAccounts()
  const { data: contacts } = useResourceList<Contact>("/contacts")

  const nameById = new Map((contacts ?? []).map((c) => [c.id, c.name]))
  const beneficiaryName = (id: string) =>
    nameById.get(id) ?? `Beneficiary ${id.slice(0, 8)}`

  const columns: DataTableColumn<AccountsDistribution>[] = [
    {
      key: "beneficiary",
      header: "Beneficiary",
      value: (row) => beneficiaryName(row.beneficiary_id),
    },
    {
      key: "share",
      header: "Share of residue",
      value: (row) => row.residuary_share,
      render: (row) => formatShare(row.residuary_share, row.residuary_share),
      align: "right",
    },
    {
      key: "entitlement",
      header: "Entitlement",
      value: (row) => row.entitlement,
      render: (row) => moneyCell(row.entitlement),
      align: "right",
    },
    {
      key: "interim_received",
      header: "Interim received",
      value: (row) => row.interim_received,
      render: (row) => moneyCell(row.interim_received),
      align: "right",
    },
    {
      key: "remaining_due",
      header: "Remaining due",
      value: (row) => row.remaining_due,
      render: (row) => moneyCell(row.remaining_due),
      align: "right",
    },
  ]

  return (
    <section aria-label="Estate accounts">
      <PageHeader
        title="Estate accounts"
        description="The live trial balance and each beneficiary's share, drawn up from the registers."
      >
        <AccountsExportActions />
      </PageHeader>

      {isPending ? (
        <FigureGrid
          figures={headlineFigures}
          accounts={undefined}
          isLoading
          columnsClass="sm:grid-cols-3"
        />
      ) : accounts === null || isError ? (
        <p role="status" className="text-sm text-muted-foreground">
          The estate accounts are not available yet. They will appear here
          once the estate records are in place.
        </p>
      ) : (
        <div className="space-y-8">
          <ReconciliationLine isBalanced={accounts.is_balanced} />

          <FigureGrid
            figures={headlineFigures}
            accounts={accounts}
            columnsClass="sm:grid-cols-3"
          />

          <section aria-labelledby="trial-balance-heading" className="space-y-4">
            <h2
              id="trial-balance-heading"
              className="text-lg font-semibold tracking-tight"
            >
              Trial balance
            </h2>
            <FigureGrid
              figures={trialBalanceFigures}
              accounts={accounts}
              columnsClass="sm:grid-cols-2 lg:grid-cols-4"
            />
          </section>

          <Card>
            <CardHeader>
              <CardTitle>Distributions to residuary beneficiaries</CardTitle>
              <CardDescription>
                Each beneficiary's share of the residue, what they have
                received on account and what remains due.
              </CardDescription>
            </CardHeader>
            <CardContent
              className={
                accounts.distributions.length > 0
                  ? "grid gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]"
                  : undefined
              }
            >
              <DataTable
                columns={columns}
                rows={accounts.distributions}
                rowKey={(row) => row.beneficiary_id}
                filterable={false}
                label="Residuary distributions"
                emptyTitle="No residuary beneficiaries recorded yet."
                emptyMessage="Entitlements appear here once residuary legacies are recorded."
              />
              {accounts.distributions.length > 0 ? (
                <ShareDonut
                  slices={accounts.distributions.map((row) => ({
                    name: beneficiaryName(row.beneficiary_id),
                    share: row.residuary_share,
                  }))}
                />
              ) : null}
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  )
}
