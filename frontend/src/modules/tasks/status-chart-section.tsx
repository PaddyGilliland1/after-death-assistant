/*
  Lazy wrapper for the task status chart so the ECharts bundle only loads
  when the tasks page renders it (mirrors how accounts loads its donut).
*/

import * as React from "react"

import type { Task } from "@/lib/types"

const TaskStatusChart = React.lazy(() =>
  import("./status-chart").then((module) => ({
    default: module.TaskStatusChart,
  })),
)

export function StatusChartSection({ tasks }: { tasks: Task[] }) {
  if (tasks.length === 0) return null
  return (
    <React.Suspense fallback={null}>
      <div className="mt-4">
        <TaskStatusChart tasks={tasks} />
      </div>
    </React.Suspense>
  )
}
