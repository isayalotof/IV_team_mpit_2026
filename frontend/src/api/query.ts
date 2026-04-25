import client from './client'
import { QueryResponse } from '@/types'

export const runQuery = async (text: string, forceLlm = false, sessionId?: string, mode: 'easy' | 'expert' = 'easy') => {
  const { data } = await client.post('/query', {
    text,
    force_llm: forceLlm,
    session_id: sessionId,
    mode,
  })
  return data as QueryResponse
}

export const getTemplates = async () => {
  const { data } = await client.get('/query/templates')
  return data.templates as { id: string; title: string; description: string; example: string; slots: string[] }[]
}

export const getSchema = async () => {
  const { data } = await client.get('/query/schema')
  return data
}
