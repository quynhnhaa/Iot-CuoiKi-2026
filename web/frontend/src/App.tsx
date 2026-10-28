import { useEffect, useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

import { Icon, type IconName } from './components/Icon'
import { UserMenu } from './components/UserMenu'
import type { Role } from './lib/api'
import { useAuth } from './lib/auth'
import { LoginPage } from './pages/LoginPage'

type NavEntry = { to: string; label: string; icon: IconName; roles?: Role[] }

const NAV: NavEntry[] = [
  { to: '/batches', label: 'Mẻ đếm', icon: 'batches' },
  { to: '/stats', label: 'Thống kê', icon: 'chart' },
  { to: '/targets', label: 'Mẫu chuẩn', icon: 'targets' },
  { to: '/users', label: 'Tài khoản', icon: 'users', roles: ['admin'] },
]

export function App() {
  const { user, loading, can } = useAuth()
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  // Trên màn hình nhỏ, menu là ngăn trượt — đổi trang thì đóng lại.
  useEffect(() => setMenuOpen(false), [location.pathname])

  if (loading) {
    return (
      <div className="loading-page">
        <span className="spinner" />
        Đang kiểm tra phiên đăng nhập…
      </div>
    )
  }

  if (!user) return <LoginPage />

  const visible = NAV.filter((entry) => !entry.roles || can(...entry.roles))
  const current = visible.find((entry) => location.pathname.startsWith(entry.to))

  return (
    <div className="app">
      {menuOpen && (
        <button
          type="button"
          className="scrim"
          aria-label="Đóng menu"
          onClick={() => setMenuOpen(false)}
        />
      )}

      <aside className={`sidebar${menuOpen ? ' open' : ''}`}>
        <div className="sidebar-brand">
          <span className="sidebar-mark">
            <Icon name="pill" size={17} />
          </span>
          <span className="sidebar-brand-text">
            <span className="sidebar-brand-title">Máy đếm viên</span>
            <span className="sidebar-brand-sub">Bảng quản lý</span>
          </span>
        </div>

        <nav className="sidebar-nav">
          <span className="sidebar-section-label">Vận hành</span>
          {visible
            .filter((entry) => !entry.roles)
            .map((entry) => (
              <NavLink key={entry.to} to={entry.to} className="nav-item">
                <Icon name={entry.icon} />
                {entry.label}
              </NavLink>
            ))}

          {can('admin') && (
            <>
              <span className="sidebar-section-label">Quản trị</span>
              {visible
                .filter((entry) => entry.roles)
                .map((entry) => (
                  <NavLink key={entry.to} to={entry.to} className="nav-item">
                    <Icon name={entry.icon} />
                    {entry.label}
                  </NavLink>
                ))}
            </>
          )}
        </nav>
      </aside>

      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="btn icon-only menu-toggle"
            aria-label="Mở menu"
            onClick={() => setMenuOpen(true)}
          >
            <Icon name="menu" size={20} />
          </button>
          <span className="topbar-title">{current?.label ?? 'Bảng quản lý'}</span>
          <span className="topbar-spacer" />
          <UserMenu />
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
