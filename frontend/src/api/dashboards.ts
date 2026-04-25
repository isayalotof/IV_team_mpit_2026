import client from './client'
import { Dashboard, DashboardWidget, DashboardWidgetResult } from '@/types'

export const listDashboards = async () => {
  const { data } = await client.get('/dashboards')
  return data.dashboards as Dashboard[]
}

export const createDashboard = async (payload: {
  name: string
  description?: string
  is_public?: boolean
}) => {
  const { data } = await client.post('/dashboards', payload)
  return data as Dashboard
}

export const getDashboard = async (id: string) => {
  const { data } = await client.get(`/dashboards/${id}`)
  return data as Dashboard
}

export const updateDashboard = async (
  id: string,
  payload: { name?: string; description?: string; is_public?: boolean }
) => {
  const { data } = await client.patch(`/dashboards/${id}`, payload)
  return data as Dashboard
}

export const deleteDashboard = async (id: string) => {
  await client.delete(`/dashboards/${id}`)
}

export const addWidget = async (
  dashboardId: string,
  payload: { report_id: string; position?: number; title_override?: string }
) => {
  const { data } = await client.post(`/dashboards/${dashboardId}/widgets`, payload)
  return data as DashboardWidget
}

export const removeWidget = async (dashboardId: string, widgetId: string) => {
  await client.delete(`/dashboards/${dashboardId}/widgets/${widgetId}`)
}

export const reorderWidgets = async (dashboardId: string, order: string[]) => {
  await client.patch(`/dashboards/${dashboardId}/widgets/reorder`, { order })
}

export const runDashboard = async (id: string) => {
  const { data } = await client.post(`/dashboards/${id}/run`)
  return data.widgets as DashboardWidgetResult[]
}

async function _downloadPdf(url: string, filename: string) {
  const token = localStorage.getItem('token')
  const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} })
  if (!res.ok) throw new Error(`PDF export failed: ${res.status}`)
  const blob = await res.blob()
  const href = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = href
  a.download = filename
  a.click()
  URL.revokeObjectURL(href)
}

export const exportReportPdf = (reportId: string, name = 'report') => {
  _downloadPdf(`/api/v1/reports/${reportId}/export`, `${name}.pdf`).catch(console.error)
}

export const exportDashboardPdf = (dashboardId: string, name = 'dashboard') =>
  _downloadPdf(`/api/v1/dashboards/${dashboardId}/export`, `${name}.pdf`)
