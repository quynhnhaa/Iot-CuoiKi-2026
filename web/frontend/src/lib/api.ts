const BASE = import.meta.env.VITE_API_BASE ?? '/api'

const TOKEN_STORAGE_KEY = 'pill-counter.access-token'

/**
 * Token nằm trong localStorage: đủ cho bản demo, nhưng một lỗi XSS trên trang
 * này sẽ đọc được token. Khi chạy thật nên chuyển sang cookie HttpOnly + CSRF.
 */
export const tokenStore = {
  read(): string | null {
    try {
      return localStorage.getItem(TOKEN_STORAGE_KEY)
    } catch {
      return null
    }
  },
  write(token: string | null) {
    try {
      if (token === null) localStorage.removeItem(TOKEN_STORAGE_KEY)
      else localStorage.setItem(TOKEN_STORAGE_KEY, token)
    } catch {
      /* chế độ riêng tư hoặc site data bị chặn: phiên chỉ sống trong tab này */
    }
  },
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
  }
}

/** Gọi khi token hết hiệu lực để lớp giao diện đưa người dùng về trang đăng nhập. */
let onUnauthorized: (() => void) | null = null
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler
}

type RequestOptions = RequestInit & { token?: string | null; skipAuthRedirect?: boolean }

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { token, skipAuthRedirect, headers, ...init } = options
  const bearer = token === undefined ? tokenStore.read() : token

  const response = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(bearer ? { Authorization: `Bearer ${bearer}` } : {}),
      ...headers,
    },
    ...init,
  })

  if (response.status === 401 && !skipAuthRedirect) {
    tokenStore.write(null)
    onUnauthorized?.()
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new ApiError(body?.detail ?? `Lỗi ${response.status}`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

// --- Xác thực ---------------------------------------------------------------

export type Role = 'admin' | 'operator' | 'viewer' | 'machine'

export type LoginChallenge = {
  stage: 'totp_required' | 'enrollment_required'
  mfa_token: string
  expires_in_seconds: number
}

export type TokenResponse = {
  access_token: string
  token_type: string
  expires_in_seconds: number
  role: Role
  username: string
}

export type EnrollmentConfirm = TokenResponse & { recovery_codes: string[] }

export type Me = {
  id: number
  username: string
  full_name: string | null
  role: Role
  totp_enabled: boolean
  last_login_at: string | null
  unused_recovery_codes: number
}

// --- Dữ liệu nghiệp vụ ------------------------------------------------------

export type Target = {
  id: number
  code: string
  name: string
  recognition_label: string | null
  note: string | null
  created_at: string
}

export type BatchStatus = 'pending' | 'running' | 'paused' | 'done' | 'aborted'

export type Batch = {
  id: number
  target_id: number
  requested_count: number
  status: BatchStatus
  operator: string | null
  note: string | null
  created_at: string
  started_at: string | null
  finished_at: string | null
}

export type Route = 'EMPTY_FRAME' | 'MULTIPLE_PILLS' | 'WRONG_DRUG' | 'DEFECTIVE' | 'ACCEPTED'

export type BatchCounters = {
  observed: Record<Route, number>
  confirmed: Record<Route, number>
  confirmed_total: number
}

export type BatchDetail = Batch & { counters: BatchCounters }

export type PillEvent = {
  id: number
  batch_id: number
  sequence: number
  pill_count: number
  image_usable: boolean
  identity_verified: boolean
  target_matches: boolean
  defect_status: string
  identity_gate_validated: boolean
  hardware_ready: boolean
  route: Route
  release_allowed: boolean
  requires_drop_confirmation: boolean
  reason: string
  drop_confirmed: boolean
  image_path: string | null
  created_at: string
}

export type User = {
  id: number
  username: string
  full_name: string | null
  role: Role
  is_active: boolean
  totp_enabled: boolean
  created_at: string
  last_login_at: string | null
  locked_until: string | null
  note: string | null
}

export type UserCreated = User & { api_key: string | null }

export const api = {
  health: () => request<Record<string, unknown>>('/health', { token: null }),

  // Bước một. Không trả access token; mfa_token chỉ dùng cho bước hai.
  login: (username: string, password: string) =>
    request<LoginChallenge>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ username, password }),
      token: null,
      skipAuthRedirect: true,
    }),

  // Bước hai.
  verifyTotp: (mfaToken: string, code: string) =>
    request<TokenResponse>('/auth/login/verify', {
      method: 'POST',
      body: JSON.stringify({ code }),
      token: mfaToken,
      skipAuthRedirect: true,
    }),

  verifyRecoveryCode: (mfaToken: string, recoveryCode: string) =>
    request<TokenResponse>('/auth/login/recovery', {
      method: 'POST',
      body: JSON.stringify({ recovery_code: recoveryCode }),
      token: mfaToken,
      skipAuthRedirect: true,
    }),

  enroll: (mfaToken: string) =>
    request<{ secret: string; otpauth_uri: string }>('/auth/totp/enroll', {
      method: 'POST',
      token: mfaToken,
      skipAuthRedirect: true,
    }),

  confirmEnrollment: (mfaToken: string, code: string) =>
    request<EnrollmentConfirm>('/auth/totp/confirm', {
      method: 'POST',
      body: JSON.stringify({ code }),
      token: mfaToken,
      skipAuthRedirect: true,
    }),

  me: () => request<Me>('/auth/me'),

  changePassword: (currentPassword: string, newPassword: string) =>
    request<void>('/auth/password', {
      method: 'POST',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  listTargets: () => request<Target[]>('/targets'),
  createTarget: (payload: {
    code: string
    name: string
    recognition_label?: string | null
    note?: string | null
  }) => request<Target>('/targets', { method: 'POST', body: JSON.stringify(payload) }),

  listBatches: () => request<Batch[]>('/batches'),
  getBatch: (id: number) => request<BatchDetail>(`/batches/${id}`),
  createBatch: (payload: { target_id: number; requested_count: number; operator?: string }) =>
    request<Batch>('/batches', { method: 'POST', body: JSON.stringify(payload) }),
  setBatchStatus: (id: number, status: BatchStatus) =>
    request<Batch>(`/batches/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),

  listEvents: (batchId: number) => request<PillEvent[]>(`/batches/${batchId}/events`),
  confirmDrop: (batchId: number, eventId: number, dropConfirmed: boolean) =>
    request<PillEvent>(`/batches/${batchId}/events/${eventId}/drop`, {
      method: 'PATCH',
      body: JSON.stringify({ drop_confirmed: dropConfirmed }),
    }),

  listUsers: () => request<User[]>('/users'),
  createUser: (payload: {
    username: string
    role: Role
    full_name?: string | null
    password?: string | null
  }) => request<UserCreated>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  updateUser: (id: number, payload: { is_active?: boolean; role?: Role }) =>
    request<User>(`/users/${id}`, { method: 'PATCH', body: JSON.stringify(payload) }),
  resetTotp: (id: number) => request<User>(`/users/${id}/reset-totp`, { method: 'POST' }),
  rotateApiKey: (id: number) =>
    request<UserCreated>(`/users/${id}/rotate-api-key`, { method: 'POST' }),
}
