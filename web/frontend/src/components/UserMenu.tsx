import { useEffect, useRef, useState } from 'react'

import { useAuth } from '../lib/auth'
import { Icon } from './Icon'
import { ROLE_LABEL } from './ui'

export function UserMenu() {
  const { user, signOut } = useAuth()
  const [open, setOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  // Đóng menu khi bấm ra ngoài hoặc nhấn Esc — hành vi menu quen tay.
  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  if (!user) return null

  const initials = user.username.slice(0, 2)
  const lowRecoveryCodes = user.role !== 'machine' && user.unused_recovery_codes <= 2

  return (
    <div className="user-menu" ref={containerRef}>
      <button
        type="button"
        className="user-trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="avatar">{initials}</span>
        <span className="user-trigger-name">{user.username}</span>
        <Icon name="chevron" size={14} />
      </button>

      {open && (
        <div className="dropdown" role="menu">
          <div className="dropdown-head">
            <div className="dropdown-head-name">{user.full_name ?? user.username}</div>
            <div className="hint">{ROLE_LABEL[user.role]}</div>
          </div>

          {lowRecoveryCodes && (
            <div className="dropdown-note">
              Còn {user.unused_recovery_codes} mã dự phòng. Nhờ quản trị viên đặt lại 2FA để nhận bộ
              mã mới.
            </div>
          )}

          <button type="button" className="dropdown-item" role="menuitem" onClick={signOut}>
            <Icon name="logout" size={16} />
            Đăng xuất
          </button>
        </div>
      )}
    </div>
  )
}
