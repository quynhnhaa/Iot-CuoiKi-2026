/**
 * Bộ icon dạng SVG nội tuyến — không thêm phụ thuộc nào.
 * Nét 1.6px, khung 24, `currentColor` để icon lấy màu của chữ bên cạnh.
 */
export type IconName =
  | 'batches'
  | 'targets'
  | 'runs'
  | 'users'
  | 'menu'
  | 'close'
  | 'logout'
  | 'check'
  | 'alert'
  | 'ban'
  | 'blank'
  | 'layers'
  | 'pill'
  | 'key'
  | 'shield'
  | 'camera'
  | 'copy'
  | 'chevron'
  | 'inbox'

const PATHS: Record<IconName, JSX.Element> = {
  batches: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 9h18M9 9v11" />
    </>
  ),
  targets: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.5" />
    </>
  ),
  runs: (
    <>
      <path d="M4 18V9M10 18V5M16 18v-6M22 18h-20" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6" />
      <path d="M16 5.5a3.5 3.5 0 0 1 0 6.9M18 20c0-2.2-.8-4.2-2.1-5.6" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  close: <path d="M6 6l12 12M18 6L6 18" />,
  logout: (
    <>
      <path d="M10 5H6a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h4" />
      <path d="M15 8l4 4-4 4M19 12H9" />
    </>
  ),
  check: <path d="M4 12.5l5 5L20 6.5" />,
  alert: (
    <>
      <path d="M12 4l9 16H3z" />
      <path d="M12 10v4.5M12 17.2v.1" />
    </>
  ),
  ban: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M6 18L18 6" />
    </>
  ),
  blank: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="3" strokeDasharray="3 3" />
    </>
  ),
  layers: (
    <>
      <path d="M12 3l9 5-9 5-9-5 9-5z" />
      <path d="M3 13l9 5 9-5" />
    </>
  ),
  pill: (
    <>
      <rect x="2.5" y="8" width="19" height="8" rx="4" transform="rotate(-45 12 12)" />
      <path d="M9 9l6 6" />
    </>
  ),
  key: (
    <>
      <circle cx="8" cy="12" r="4" />
      <path d="M12 12h9M18 12v4M15.5 12v3" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3l8 3v6c0 4.4-3.3 8.2-8 9-4.7-.8-8-4.6-8-9V6z" />
      <path d="M9 12l2.2 2.2L15.5 10" />
    </>
  ),
  copy: (
    <>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M15 5H6a2 2 0 0 0-2 2v9" />
    </>
  ),
  chevron: <path d="M6 9l6 6 6-6" />,
  camera: (
    <>
      <path d="M3 8.5A1.5 1.5 0 0 1 4.5 7h2.2l1.2-2h8.2l1.2 2h2.2A1.5 1.5 0 0 1 21 8.5v9A1.5 1.5 0 0 1 19.5 19h-15A1.5 1.5 0 0 1 3 17.5z" />
      <circle cx="12" cy="13" r="3.2" />
    </>
  ),
  inbox: (
    <>
      <path d="M3 13l2.6-7.2A2 2 0 0 1 7.5 4.5h9a2 2 0 0 1 1.9 1.3L21 13v5a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <path d="M3 13h5l1 2.5h6L16 13h5" />
    </>
  ),
}

export function Icon({
  name,
  size = 18,
  className,
}: {
  name: IconName
  size?: number
  className?: string
}) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {PATHS[name]}
    </svg>
  )
}
