import client from './client'
import { Report, QueryResponse } from '@/types'

export const listReports = async (scope: 'all' | 'mine' | 'public' = 'all') => {
  const { data } = await client.get(`/reports?scope=${scope}`)
  return data.reports as Report[]
}

export const getReport = async (id: string) => {
  const { data } = await client.get(`/reports/${id}`)
  return data as Report
}

export const createReport = async (payload: {
  name: string
  description?: string
  sql: string
  original_question?: string
  is_public?: boolean
  interpretation?: object
  chart_config?: object
  columns_meta?: object[]
}) => {
  const { data } = await client.post('/reports', payload)
  return data as Report
}

export const updateReport = async (id: string, payload: { name?: string; description?: string; is_public?: boolean }) => {
  const { data } = await client.patch(`/reports/${id}`, payload)
  return data as Report
}

export const deleteReport = async (id: string) => {
  await client.delete(`/reports/${id}`)
}

export const runReport = async (id: string) => {
  const { data } = await client.post(`/reports/${id}/run`)
  return data as QueryResponse & { report_id: string }
}
