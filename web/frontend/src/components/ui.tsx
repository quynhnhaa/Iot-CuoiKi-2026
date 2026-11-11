import type { ReactNode } from 'react'

import type { BatchStatus, Role, Route } from '../lib/api'
import { Icon, type IconName } from './Icon'

/** Bốn màu trạng thái, cộng một bậc trung tính. Màu không bao giờ đứng một mình. */
export type Status = 'good' | 'warning' | 'serious' | 'critical' | 'neutral'

type StatusLook = { status: Status; icon: IconName; label: string }

/**
 * `droppable` = nhãn này có lúc nào được phép thả viên xuống ô không.
 *
 * Lấy thẳng từ `decision_simulator`: WRONG_DRUG, MULTIPLE_PILLS và EMPTY_FRAME
 * luôn trả `release_allowed=false`, nên máy không bao giờ thả chúng, nên cảm
 * biến đường rơi không bao giờ có gì để xác nhận — số "đã xác nhận" của ba
 * nhãn này vĩnh viễn bằng 0. Giao diện phải biết điều đó, nếu không nó sẽ hiện
 * một số 0 to đùng ở ô "Sai thuốc" trong khi camera vừa bắt được một viên sai.
 */
type RouteLook = StatusLook & { droppable: boolean }

/**
 * Năm ô đích là *trạng thái*, không phải năm chuỗi dữ liệu — nên dùng bảng màu
 * trạng thái, mỗi màu đi kèm icon và nhãn chữ.
 */
export const ROUTE_LOOK: Record<Route, RouteLook> = {
  ACCEPTED: { status: 'good', icon: 'check', label: 'Đúng, nguyên', droppable: true },
  DEFECTIVE: { status: 'warning', icon: 'alert', label: 'Sứt, vỡ', droppable: true },
  WRONG_DRUG: { status: 'critical', icon: 'ban', label: 'Sai thuốc', droppable: false },
  MULTIPLE_PILLS: { status: 'serious', icon: 'layers', label: 'Nhiều viên', droppable: false },
  EMPTY_FRAME: { status: 'neutral', icon: 'blank', label: 'Khung trống', droppable: false },
}

export const BATCH_STATUS_LOOK: Record<BatchStatus, StatusLook> = {
  pending: { status: 'neutral', icon: 'blank', label: 'Chờ chạy' },
  running: { status: 'good', icon: 'check', label: 'Đang chạy' },
  paused: { status: 'warning', icon: 'alert', label: 'Tạm dừng' },
  done: { status: 'neutral', icon: 'check', label: 'Xong' },
  aborted: { status: 'critical', icon: 'ban', label: 'Đã huỷ' },
}

export const ROLE_LABEL: Record<Role, string> = {
  admin: 'Quản trị',
  operator: 'Vận hành',
  viewer: 'Chỉ xem',
  machine: 'Thiết bị',
}

export function Badge({
  status = 'neutral',
  icon,
  children,
  outline,
}: {
  status?: Status
  icon?: IconName
  children: ReactNode
  outline?: boolean
}) {
  const classes = ['badge', outline ? 'outline' : status].filter(Boolean).join(' ')
  return (
    <span className={classes}>
      {icon && <Icon name={icon} size={13} />}
      {children}
    </span>
  )
}

export function RouteBadge({ route }: { route: Route }) {
  const look = ROUTE_LOOK[route]
  return (
    <Badge status={look.status} icon={look.icon}>
      {look.label}
    </Badge>
  )
}

export function BatchStatusBadge({ status }: { status: BatchStatus }) {
  const look = BATCH_STATUS_LOOK[status]
  return (
    <Badge status={look.status} icon={look.icon}>
      {look.label}
    </Badge>
  )
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string
  description?: string
  actions?: ReactNode
}) {
  return (
    <div className="page-header">
      <div className="page-header-text">
        <h1>{title}</h1>
        {description && <p>{description}</p>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </div>
  )
}

export function Card({
  title,
  description,
  actions,
  children,
  variant,
}: {
  title?: string
  description?: string
  actions?: ReactNode
  children: ReactNode
  variant?: 'accent' | 'caution'
}) {
  return (
    <section className={['card', variant].filter(Boolean).join(' ')}>
      {title && (
        <div className="card-header">
          <div>
            <h2>{title}</h2>
            {description && <p className="hint">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      <div className="card-body">{children}</div>
    </section>
  )
}

export function Field({
  label,
  hint,
  children,
  className,
}: {
  label: string
  hint?: string
  children: ReactNode
  className?: string
}) {
  return (
    <label className={['field', className].filter(Boolean).join(' ')}>
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  )
}

export function Alert({
  variant = 'info',
  icon = 'alert',
  children,
}: {
  variant?: 'info' | 'caution' | 'critical'
  icon?: IconName
  children: ReactNode
}) {
  return (
    <div className={`alert ${variant}`} role={variant === 'critical' ? 'alert' : undefined}>
      <Icon name={icon} size={16} />
      <div className="alert-body">{children}</div>
    </div>
  )
}

export function EmptyState({
  icon = 'inbox',
  title,
  children,
}: {
  icon?: IconName
  title: string
  children?: ReactNode
}) {
  return (
    <div className="empty">
      <span className="empty-icon">
        <Icon name={icon} size={20} />
      </span>
      <h3>{title}</h3>
      {children && <p>{children}</p>}
    </div>
  )
}

/** Ô số liệu. Một con số lớn thì không cần biểu đồ. */
export function Tile({
  label,
  value,
  sub,
  status,
  dim,
}: {
  label: string
  value: number | string
  sub?: string
  status?: Status
  dim?: boolean
}) {
  return (
    <div className={['tile', dim ? 'dim' : null].filter(Boolean).join(' ')}>
      <div className="tile-label">
        {status && <span className={`dot ${status}`} />}
        {label}
      </div>
      <div className="tile-value nums">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  )
}

export function Meter({
  value,
  max,
  caption,
  rightCaption,
}: {
  value: number
  max: number
  caption?: string
  rightCaption?: string
}) {
  const percent = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0
  return (
    <div className="meter">
      <div
        className="meter-track"
        role="progressbar"
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-label={caption}
      >
        <div className="meter-fill" style={{ width: `${percent}%` }} />
      </div>
      {(caption || rightCaption) && (
        <div className="meter-caption">
          <span>{caption}</span>
          <span className="nums">{rightCaption}</span>
        </div>
      )}
    </div>
  )
}

export function CopyRow({ value }: { value: string }) {
  return (
    <div className="copy-row">
      <pre>{value}</pre>
      <button
        type="button"
        className="btn secondary sm"
        onClick={() => void navigator.clipboard?.writeText(value)}
      >
        <Icon name="copy" size={14} />
        Sao chép
      </button>
    </div>
  )
}
