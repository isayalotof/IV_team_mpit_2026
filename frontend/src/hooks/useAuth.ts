import { useAuthStore } from '@/store/auth'

export const useAuth = () => useAuthStore()
export const useIsRole = (minRole: 'viewer' | 'analyst' | 'admin') => useAuthStore((s) => s.isRole(minRole))
