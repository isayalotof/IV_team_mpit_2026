import {
  BarChart, Bar, LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Cell, Legend,
} from 'recharts'
import { QueryData, ChartConfig } from '@/types'

const CHART_COLORS = [
  'var(--chart-1)',
  'var(--chart-2)',
  'var(--chart-3)',
  'var(--chart-4)',
  'var(--chart-5)',
  'var(--chart-6)',
  'var(--chart-7)',
]

const COLOR_HEX = ['#E8FF5C', '#5B8CFF', '#BC8CFF', '#5ED0D0', '#D29922', '#F85149', '#3FB950']

interface Props {
  data: QueryData
  chart: ChartConfig
}

function buildChartData(data: QueryData): Record<string, unknown>[] {
  return data.rows.map((row) => {
    const obj: Record<string, unknown> = {}
    data.columns.forEach((col, i) => {
      obj[col.name] = row[i]
    })
    return obj
  })
}

function formatTick(value: unknown): string {
  if (typeof value === 'number') {
    if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`
    if (value >= 1_000) return `${(value / 1_000).toFixed(0)}K`
    return String(value)
  }
  if (typeof value === 'string' && value.length > 12) return value.slice(0, 12) + '…'
  return String(value ?? '')
}

const tooltipStyle = {
  backgroundColor: 'var(--bg-elevated)',
  border: '1px solid var(--border-default)',
  borderRadius: 6,
  color: 'var(--text-primary)',
  fontSize: 12,
  fontFamily: 'var(--font-mono)',
}

const MAX_BAR_ROWS = 50
const MAX_STACKED_ROWS = 15

export function ResultChart({ data, chart }: Props) {
  const chartData = buildChartData(data)

  if (chart.type === 'kpi') {
    const value = data.rows[0]?.[0]
    return (
      <div style={{ padding: '40px 20px', textAlign: 'center' }}>
        <div style={{
          fontFamily: 'var(--font-serif)', fontSize: 120, lineHeight: 1,
          letterSpacing: '-0.04em', color: 'var(--accent)',
        }}>
          {formatTick(value)}
        </div>
        <div style={{
          fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--text-muted)',
          textTransform: 'uppercase', letterSpacing: '0.15em', marginTop: 12,
        }}>
          {chart.label || data.columns[0]?.name}
        </div>
      </div>
    )
  }

  // Bar chart — use custom bar-rows design when data has clear label+value structure
  if (chart.type === 'bar' && chart.x && chart.y) {
    if (chartData.length > MAX_BAR_ROWS) return null
    const xCol = chart.x
    const yCol = chart.y
    const values = chartData.map(d => Number(d[yCol]) || 0)
    const maxVal = Math.max(...values, 1)

    // Use custom bar-rows for up to 20 items, recharts for more
    if (chartData.length <= 20) {
      return (
        <div className="bar-rows">
          {chartData.map((row, i) => {
            const val = Number(row[yCol]) || 0
            const pct = (val / maxVal) * 100
            const label = String(row[xCol] || '').slice(0, 14)
            const colorIdx = i % 7
            return (
              <div className="bar-row" key={i}>
                <div className="bar-label" title={String(row[xCol])}>{label}</div>
                <div className="bar-track">
                  <div
                    className={`bar-fill idx-${colorIdx}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <div className="bar-val">
                  {formatTick(val)}
                </div>
              </div>
            )
          })}
        </div>
      )
    }

    // Recharts for many rows
    return (
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis
            dataKey={xCol}
            tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            tickFormatter={formatTick}
            axisLine={{ stroke: 'var(--border-default)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            tickFormatter={formatTick}
            axisLine={false}
            tickLine={false}
            width={50}
          />
          <Tooltip contentStyle={tooltipStyle} formatter={(v) => [formatTick(v), yCol]} />
          <Bar dataKey={yCol} radius={[3, 3, 0, 0]}>
            {chartData.map((_, i) => (
              <Cell key={i} fill={COLOR_HEX[i % COLOR_HEX.length]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    )
  }

  if (chart.type === 'line' && chart.x && chart.y) {
    return (
      <div style={{ width: '100%', height: 260, overflow: 'hidden' }}>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
            <XAxis
              dataKey={chart.x}
              tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              tickFormatter={(v) => {
                if (typeof v === 'string' && v.length > 10 && v.includes('-')) return v.slice(0, 10)
                return formatTick(v)
              }}
              axisLine={{ stroke: 'var(--border-default)' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              tickFormatter={formatTick}
              axisLine={false}
              tickLine={false}
              width={55}
              domain={['auto', 'auto']}
            />
            <Tooltip contentStyle={tooltipStyle} />
            <Line
              type="monotone"
              dataKey={chart.y!}
              stroke="#E8FF5C"
              strokeWidth={2.5}
              dot={false}
              activeDot={{ r: 4, fill: '#E8FF5C' }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    )
  }

  if (chart.type === 'line_multi' && chart.x && chart.y && chart.series) {
    // Group data by series value, draw one line per series
    const seriesValues = [...new Set(chartData.map(d => String(d[chart.series!] ?? '')))]
    const pivoted: Record<string, unknown>[] = []
    const xValues = [...new Set(chartData.map(d => d[chart.x!]))]
    for (const xVal of xValues) {
      const entry: Record<string, unknown> = { [chart.x!]: xVal }
      for (const sv of seriesValues) {
        const found = chartData.find(d => d[chart.x!] === xVal && String(d[chart.series!]) === sv)
        entry[sv] = found ? Number(found[chart.y!]) || 0 : null
      }
      pivoted.push(entry)
    }
    return (
      <div style={{ width: '100%', height: 260, overflow: 'hidden' }}>
      <ResponsiveContainer width="100%" height={260}>
        <LineChart data={pivoted} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
          <XAxis
            dataKey={chart.x}
            tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            tickFormatter={formatTick}
            axisLine={{ stroke: 'var(--border-default)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
            tickFormatter={formatTick}
            axisLine={false}
            tickLine={false}
            width={50}
          />
          <Tooltip contentStyle={tooltipStyle} formatter={(v) => [formatTick(v), '']} />
          <Legend wrapperStyle={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: 'var(--text-muted)' }} />
          {seriesValues.slice(0, 7).map((sv, i) => (
            <Line
              key={sv}
              type="monotone"
              dataKey={sv}
              stroke={COLOR_HEX[i % COLOR_HEX.length]}
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
      </div>
    )
  }

  if (chart.type === 'stacked' && chart.x && chart.y_cols && chart.y_cols.length > 0) {
    if (chartData.length > MAX_STACKED_ROWS) return null
    return (
      <div style={{ width: '100%', height: 260, overflow: 'hidden' }}>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={chartData} margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle)" vertical={false} />
            <XAxis
              dataKey={chart.x}
              tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              tickFormatter={formatTick}
              axisLine={{ stroke: 'var(--border-default)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: 'var(--text-muted)', fontSize: 11, fontFamily: 'JetBrains Mono' }}
              tickFormatter={formatTick}
              axisLine={false}
              tickLine={false}
              width={50}
            />
            <Tooltip contentStyle={tooltipStyle} formatter={(v, name) => [formatTick(v), name]} />
            <Legend wrapperStyle={{ fontSize: 11, fontFamily: 'JetBrains Mono', color: 'var(--text-muted)' }} />
            {chart.y_cols.map((col, i) => (
              <Bar key={col} dataKey={col} stackId="a" fill={COLOR_HEX[i % COLOR_HEX.length]} radius={i === chart.y_cols!.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    )
  }

  return null
}
