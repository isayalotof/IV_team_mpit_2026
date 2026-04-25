import client from './client'

export const addRagExample = async (question: string, sql: string) => {
  const { data } = await client.post('/admin/rag', { question, sql })
  return data as { id: string; ok: boolean }
}
