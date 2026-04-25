import { create } from 'zustand'
import { User } from '@/types'

interface AuthState {
  user: User | null
  token: string | null
  setAuth: (user: User, token: string) => void
  clearAuth: () => void
  isRole: (minRole: 'viewer' | 'analyst' | 'admin') => boolean
}

const ROLE_HIERARCHY = { viewer: 0, analyst: 1, admin: 2 }

const storedUser = localStorage.getItem('user')
const storedToken = localStorage.getItem('token')

export const useAuthStore = create<AuthState>((set, get) => ({
  user: storedUser ? JSON.parse(storedUser) : null,
  token: storedToken,
  setAuth: (user, token) => {
    localStorage.setItem('user', JSON.stringify(user))
    localStorage.setItem('token', token)
    set({ user, token })
  },
  clearAuth: () => {
    localStorage.removeItem('user')
    localStorage.removeItem('token')
    set({ user: null, token: null })
  },
  isRole: (minRole) => {
    const { user } = get()
    if (!user) return false
    return (ROLE_HIERARCHY[user.role] ?? -1) >= (ROLE_HIERARCHY[minRole] ?? 999)
  },
}))
