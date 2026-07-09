/*
  Donut of residuary shares, the first chart in the app. ECharts with the
  SVG renderer and modular imports so only the pie pieces are bundled.

  Accessibility: the rendered chart is a labelled image (role img) and a
  visually hidden table beside it carries the exact same data for screen
  readers, so nothing depends on the graphic or on colour alone.

  Colour: a validated categorical palette (light and dark selected
  separately), hues assigned in fixed order and never cycled; a ninth or
  later beneficiary folds into "Other" in the chart only, while the
  hidden table remains the exact record.
*/

import * as React from "react"
import { PieChart } from "echarts/charts"
import { LegendComponent, TooltipComponent } from "echarts/components"
import * as echarts from "echarts/core"
import { SVGRenderer } from "echarts/renderers"
import ReactEChartsCore from "echarts-for-react/lib/core"

import { formatShare } from "./money"

echarts.use([PieChart, TooltipComponent, LegendComponent, SVGRenderer])

export interface ShareSlice {
  name: string
  /** Decimal share fraction as returned by the API, for example "0.5". */
  share: string
}

interface ChartTheme {
  surface: string
  ink: string
  series: string[]
}

const LIGHT: ChartTheme = {
  surface: "#fcfcfb",
  ink: "#52514e",
  series: [
    "#2a78d6",
    "#1baf7a",
    "#eda100",
    "#008300",
    "#4a3aa7",
    "#e34948",
    "#e87ba4",
    "#eb6834",
  ],
}

const DARK: ChartTheme = {
  surface: "#1a1a19",
  ink: "#c3c2b7",
  series: [
    "#3987e5",
    "#199e70",
    "#c98500",
    "#008300",
    "#9085e9",
    "#e66767",
    "#d55181",
    "#d95926",
  ],
}

/** Tracks the app's .dark class so the chart follows the active theme. */
function useIsDark(): boolean {
  const [isDark, setIsDark] = React.useState(() =>
    document.documentElement.classList.contains("dark"),
  )

  React.useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"))
    })
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    })
    return () => observer.disconnect()
  }, [])

  return isDark
}

const MAX_SLICES = 8

/**
 * Chart geometry needs numbers, so shares are parsed here and nowhere
 * else; the hidden table shows the API's exact figures. Beyond eight
 * slices the remainder folds into "Other" so hues are never cycled.
 */
function toChartData(slices: ShareSlice[]): { name: string; value: number }[] {
  const numeric = slices.map((slice) => ({
    name: slice.name,
    value: Number(slice.share) || 0,
  }))
  if (numeric.length <= MAX_SLICES) return numeric
  const kept = numeric.slice(0, MAX_SLICES - 1)
  const rest = numeric.slice(MAX_SLICES - 1)
  return [
    ...kept,
    { name: "Other", value: rest.reduce((sum, slice) => sum + slice.value, 0) },
  ]
}

export function ShareDonut({ slices }: { slices: ShareSlice[] }) {
  const isDark = useIsDark()
  const theme = isDark ? DARK : LIGHT
  const data = toChartData(slices)

  const option = {
    color: theme.series,
    tooltip: {
      trigger: "item" as const,
      formatter: "{b}: {d}%",
    },
    legend: {
      bottom: 0,
      icon: "circle",
      textStyle: { color: theme.ink },
    },
    series: [
      {
        type: "pie" as const,
        radius: ["55%", "80%"],
        center: ["50%", "44%"],
        avoidLabelOverlap: true,
        itemStyle: {
          borderColor: theme.surface,
          borderWidth: 2,
          borderRadius: 4,
        },
        label: {
          // Direct labels only while they stay readable; the legend
          // always carries identity.
          show: data.length <= 4,
          formatter: "{b}",
          color: theme.ink,
        },
        labelLine: { lineStyle: { color: theme.ink } },
        data,
      },
    ],
  }

  return (
    <div>
      <div
        role="img"
        aria-label={`Donut chart of residuary shares across ${slices.length} ${
          slices.length === 1 ? "beneficiary" : "beneficiaries"
        }. The same data follows as a table.`}
      >
        <ReactEChartsCore
          echarts={echarts}
          option={option}
          notMerge
          style={{ height: 260 }}
          opts={{ renderer: "svg" }}
        />
      </div>
      <table className="sr-only">
        <caption>Residuary shares by beneficiary</caption>
        <thead>
          <tr>
            <th scope="col">Beneficiary</th>
            <th scope="col">Share of residue</th>
          </tr>
        </thead>
        <tbody>
          {slices.map((slice) => (
            <tr key={slice.name}>
              <th scope="row">{slice.name}</th>
              <td>{formatShare(slice.share, slice.share)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
