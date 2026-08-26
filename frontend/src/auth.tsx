import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { getCurrentUser, login as loginRequest, logout as logoutRequest } from './api'
import type { CurrentUser, Role } from './api/contracts'

type AuthState = {
  user: CurrentUser | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  hasRole: (role: Role) => boolean
}

const AuthContext = createContext<AuthState | null>(null)
const ranks: Record<Role, number> = { viewer: 0, editor: 1, admin: 2 }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    getCurrentUser().then(setUser).catch(() => setUser(null)).finally(() => setLoading(false))
  }, [])
  useEffect(() => {
    const clearSession = () => setUser(null)
    window.addEventListener('office-cook:unauthorized', clearSession)
    return () => window.removeEventListener('office-cook:unauthorized', clearSession)
  }, [])
  const value: AuthState = {
    user,
    loading,
    login: async (username, password) => { setUser(await loginRequest(username, password)) },
    logout: async () => { await logoutRequest(); setUser(null) },
    hasRole: (role) => user !== null && ranks[user.role] >= ranks[role],
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const value = useContext(AuthContext)
  if (!value) throw new Error('useAuth must be used inside AuthProvider')
  return value
}
