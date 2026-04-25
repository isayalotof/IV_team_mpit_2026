export interface User {
  id: number
  username: string
  role: 'viewer' | 'analyst' | 'admin'
}

export interface Column {
  name: string
  type: string
}

export interface QueryData {
  columns: Column[]
  rows: (string | number | null)[][]
  row_count: number
}

export interface ChartConfig {
  type: 'bar' | 'line' | 'line_multi' | 'kpi' | 'table' | 'stacked'
  x?: string
  y?: string
  y_cols?: string[]
  series?: string
  title?: string
  value_col?: string
  label?: string
}

export interface Confidence {
  score: number
  level: 'high' | 'medium' | 'low'
  explanation: string
}

export interface Interpretation {
  metric?: string
  grouping?: string
  period?: { label: string; from?: string; to?: string }
  filters: string[]
}

export interface QueryResponse {
  status: 'ok' | 'ambiguous' | 'error'
  query_id?: string
  sql?: string
  sql_source?: 'template' | 'llm' | 'llm_corrected'
  template_id?: string
  interpretation?: Interpretation
  explanation?: string
  data?: QueryData
  chart?: ChartConfig
  confidence?: Confidence
  execution_ms?: number
  warnings?: string[]
  suggestions?: { text: string; query?: string }[]
  error_code?: string
  detail?: string
}

export interface Report {
  id: string
  name: string
  description?: string
  owner: { id: number; username: string }
  is_public: boolean
  created_at: string
  last_run_at?: string
  chart_type?: string
  has_schedule?: boolean
  original_question?: string
  sql?: string
  interpretation?: Interpretation
  chart_config?: ChartConfig
}

export interface Schedule {
  id: string
  report_id: string
  cron: string
  timezone: string
  delivery_type: 'telegram' | 'email' | 'none'
  delivery_targets: string[]
  enabled: boolean
  created_at: string
  last_run_at?: string
  last_run_status?: string
}

export interface ChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: number
  role: 'user' | 'assistant'
  content: string
  query_response?: QueryResponse
  created_at: string
}

export interface Dashboard {
  id: string
  name: string
  description?: string
  owner: { id: number; username: string }
  is_public: boolean
  created_at: string
  updated_at: string
  widgets?: DashboardWidget[]
}

export interface DashboardWidget {
  id: string
  dashboard_id: string
  report_id: string
  position: number
  title_override?: string
  created_at: string
  report?: Report
}

export interface DashboardWidgetResult {
  widget_id: string
  report_id: string
  title: string
  data?: { columns: Column[]; rows: (string | number | null)[][]; row_count: number }
  chart?: ChartConfig
  sql?: string
  error?: string
}

export interface AuditLog {
  id: number
  user_id: number
  question: string
  sql_source?: string
  confidence?: number
  rows_returned?: number
  violations?: string[]
  error?: string
  created_at: string
}
