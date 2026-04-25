import client from './client'
import { Schedule } from '@/types'

export const listSchedules = async () => {
  const { data } = await client.get('/schedules')
  return data.schedules as Schedule[]
}

export const createSchedule = async (payload: {
  report_id: string
  cron: string
  timezone?: string
  delivery_type: 'telegram' | 'email' | 'none'
  delivery_targets: string[]
  enabled?: boolean
}) => {
  const { data } = await client.post('/schedules', payload)
  return data as Schedule
}

export const updateSchedule = async (id: string, payload: Partial<Schedule>) => {
  const { data } = await client.patch(`/schedules/${id}`, payload)
  return data as Schedule
}

export const deleteSchedule = async (id: string) => {
  await client.delete(`/schedules/${id}`)
}
