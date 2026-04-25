import client from './client'
import { User } from '@/types'

export const login = async (username: string, password: string) => {
  const { data } = await client.post('/auth/login', { username, password })
  return data as { access_token: string; user: User }
}

export const getMe = async () => {
  const { data } = await client.get('/auth/me')
  return data as User
}
