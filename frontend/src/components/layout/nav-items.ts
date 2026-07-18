import {
  Activity,
  Banknote,
  BookOpen,
  Calculator,
  ClipboardList,
  FileSignature,
  FileText,
  HeartHandshake,
  Landmark,
  LayoutDashboard,
  ListChecks,
  Medal,
  MonitorSmartphone,
  Receipt,
  Scale,
  ScrollText,
  Search,
  Settings,
  Shield,
  Users,
  type LucideIcon,
} from "lucide-react"

export interface NavItem {
  label: string
  to: string
  icon: LucideIcon
}

export interface NavGroup {
  label: string
  items: NavItem[]
}

/*
  One entry per module. Paths use hyphens; module directories use the
  underscore names from the build contract.
*/
export const navGroups: NavGroup[] = [
  {
    label: "Overview",
    items: [{ label: "Dashboard", to: "/", icon: LayoutDashboard }],
  },
  {
    label: "Records",
    items: [
      { label: "Tasks", to: "/tasks", icon: ListChecks },
      { label: "Assets", to: "/assets", icon: Landmark },
      { label: "Debtors and creditors", to: "/debtors-creditors", icon: Scale },
      { label: "Contacts", to: "/contacts", icon: Users },
      { label: "Costs", to: "/costs", icon: Receipt },
      { label: "Documents", to: "/documents", icon: FileText },
    ],
  },
  {
    label: "Money and tax",
    items: [
      { label: "Estate accounts", to: "/accounts", icon: Banknote },
      { label: "Inheritance tax", to: "/iht", icon: Calculator },
      { label: "Reliefs", to: "/reliefs", icon: ScrollText },
      { label: "Administration tax", to: "/admin-tax", icon: ClipboardList },
    ],
  },
  {
    label: "Guidance",
    items: [
      { label: "Knowledge library", to: "/knowledge", icon: BookOpen },
      { label: "When you need help", to: "/help", icon: HeartHandshake },
      { label: "Drafts", to: "/drafts", icon: FileSignature },
      { label: "Timeline", to: "/timeline", icon: Activity },
    ],
  },
  {
    label: "Further work",
    items: [
      { label: "Asset tracing", to: "/tracing", icon: Search },
      { label: "Digital assets", to: "/digital", icon: MonitorSmartphone },
      { label: "Veteran checklist", to: "/veteran", icon: Medal },
      { label: "Executor protection", to: "/executor", icon: Shield },
    ],
  },
  {
    label: "Administration",
    items: [{ label: "Settings and audit", to: "/admin", icon: Settings }],
  },
]

export const allNavItems: NavItem[] = navGroups.flatMap((group) => group.items)
