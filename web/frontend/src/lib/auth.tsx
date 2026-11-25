import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'

import { api, setUnauthorizedHandler, tokenStore, type Me, type Role } from './api'

type AuthState = {
  user: Me | null
  loading: boolean
  signIn: (token: string) => Promise<void>
  signOut: () => void
  refresh: () => Promise<void>
  can: (...roles: Role[]) => boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Me | null>(null)
  const [loading, setLoading] = useState(true)

  const signOut = useCallback(() => {
    tokenStore.write(null)
    setUser(null)
  }, [])

  const refresh = useCallback(async () => {
    if (!tokenStore.read()) {
      setUser(null)
      setLoading(false)
      return
    }
    try {
      setUser(await api.me())
    } catch {
      // Token hết hạn hoặc bị thu hồi; api.ts đã xoá nó.
      setUser(null)
    } finally {
      setLoading(false)
    }
  }, [])

  const signIn = useCallback(
    async (token: string) => {
      tokenStore.write(token)
      setLoading(true)
      await refresh()
    },
    [refresh],
  )

  useEffect(() => {
    // Backend thu hồi token (đổi mật khẩu, bị vô hiệu) thì đưa về đăng nhập ngay.
    setUnauthorizedHandler(() => setUser(null))
    return () => setUnauthorizedHandler(null)
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  const value = useMemo<AuthState>(
    () => ({
      user,
      loading,
      signIn,
      signOut,
      refresh,
      can: (...roles: Role[]) => (user ? roles.includes(user.role) : false),
    }),
    [user, loading, signIn, signOut, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext)
  if (!context) throw new Error('useAuth phải nằm trong AuthProvider')
  return context
}

/**
 * Gạn giao diện theo vai trò chỉ để bớt rối mắt. Quyết định thật nằm ở backend —
 * mỗi route đều có guard riêng, nên ẩn một nút không phải là cơ chế bảo vệ.
 */
export function RoleGate({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { can } = useAuth()
  return can(...roles) ? <>{children}</> : null
}
