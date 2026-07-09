/*
  Task status chart: a small donut of open work by status, following the
  accounts share-donut pattern exactly (SVG renderer, modular imports,
  fixed-order validated palette, dark mode via the .dark class, and a
  visually hidden table carrying the same data for screen readers).
*/

import * as React from "react"
import { PieChart } from "echarts/charts"
import { LegendComponent, TooltipComponent } from "echarts/components"
import * as echarts from "echarts/core"
import { SVGRenderer } from "echarts/renderers"
import ReactEChartsCore from "echarts-for-react/lib/core"

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import type { Task } from "@/lib/types"

import { statusLabel } from "./task-meta"

echarts.use([PieChart, TooltipComponent, LegendComponent, SVGRenderer])

interface ChartTheme {
  surface: string
  ink: string
  series: string[]
}

const LIGHT: ChartTheme = {
  surface: "#fcfcfb",
  ink: "#52514e",
  series: ["#2a78d6", "#1baf7a", "#eda100", "#4a3aa7", "#e34948", "#e87ba4"],
}

const DARK: ChartTheme = {
  surface: "#1a1a19",
  ink: "#c3c2b7",
  series: ["#3987e5", "#199e70", "#c98500", "#6a5acd", "#e34948", "#e87ba4"],
}

function useIsDark(): boolean {
  const [dark, setDark] = React.useState(() =>
    document.documentElement.classList.contains("dark"),
  )
  React.useEffect(() => {
    const observer = new MutationObserver(() =>
      setDark(document.documentElement.classList.contains("dark")),
    )
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    })
    return () => observer.disconnect()
  }, [])
  return dark
}

export function TaskStatusChart({ tasks }: { tasks: Task[] }) {
  const isDark = useIsDark()
  const theme = isDark ? DARK : LIGHT

  const counts = new Map<string, number>()
  for (const task of tasks) {
    const label = statusLabel(task.status ?? null)
    counts.set(label, (counts.get(label) ?? 0) + 1)
  }
  const rows = [...counts.entries()].sort((a, b) => b[1] - a[1])

  if (rows.length === 0) return null

  const option = {
    backgroundColor: "transparent",
    color: theme.series,
    tooltip: { trigger: "item" },
    legend: {
      bottom: 0,
      textStyle: { color: theme.ink },
    },
    series: [
      {
        type: "pie",
        radius: ["55%", "80%"],
        top: 0,
        bottom: 24,
        avoidLabelOverlap: true,
        label: { show: false },
        data: rows.map(([name, value]) => ({ name, value })),
      },
    ],
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Tasks by status</CardTitle>
        <CardDescription>
          The spread of the {tasks.length} tasks currently on the list.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div
          role="img"
          aria-label={`Tasks by status: ${rows
            .map(([name, value]) => `${name} ${value}`)
            .join(", ")}`}
        >
          <ReactEChartsCore
            echarts={echarts}
            option={option}
            style={{ height: 220 }}
            opts={{ renderer: "svg" }}
          />
        </div>
        <table className="sr-only">
          <caption>Tasks by status</caption>
          <thead>
            <tr>
              <th scope="col">Status</th>
              <th scope="col">Tasks</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([name, value]) => (
              <tr key={name}>
                <td>{name}</td>
                <td>{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </CardContent>
    </Card>
  )
}
