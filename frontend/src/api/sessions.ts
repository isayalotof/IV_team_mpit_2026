import client from './client'
import { ChatSession, ChatMessage } from '@/types'

export const getSessions = async (): Promise<ChatSession[]> => {
  const { data } = await client.get('/sessions')
  return data.sessions
}

export const getSessionMessages = async (sessionId: string): Promise<{ title: string; messages: ChatMessage[] }> => {
  const { data } = await client.get(`/sessions/${sessionId}/messages`)
  return data
}

export const deleteSession = async (sessionId: string): Promise<void> => {
  await client.delete(`/sessions/${sessionId}`)
}
