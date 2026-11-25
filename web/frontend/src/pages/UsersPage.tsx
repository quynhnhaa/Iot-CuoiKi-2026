import { useEffect, useState } from 'react'

import {
  Alert,
  Badge,
  Card,
  CopyRow,
  EmptyState,
  Field,
  PageHeader,
  ROLE_LABEL,
} from '../components/ui'
import { api, type Role, type User } from '../lib/api'
import { useAuth } from '../lib/auth'

const HUMAN_ROLES: Role[] = ['admin', 'operator', 'viewer']
const MIN_PASSWORD_LENGTH = 12
const EMPTY_FORM = { username: '', role: 'operator' as Role, password: '' }

export function UsersPage() {
  const { user: me } = useAuth()
  const [users, setUsers] = useState<User[]>([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  // API key chỉ được trả về đúng một lần, nên phải hiện ngay tại đây.
  const [issuedKey, setIssuedKey] = useState<{ username: string; apiKey: string } | null>(null)

  async function reload() {
    setUsers(await api.listUsers())
  }

  useEffect(() => {
    reload()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function run(action: () => Promise<unknown>) {
    try {
      await action()
      setError(null)
      await reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const isMachine = form.role === 'machine'

  const createUser = () =>
    run(async () => {
      const created = await api.createUser({
        username: form.username,
        role: form.role,
        password: isMachine ? null : form.password,
      })
      if (created.api_key) setIssuedKey({ username: created.username, apiKey: created.api_key })
      setForm(EMPTY_FORM)
    })

  return (
    <div className="stack">
      <PageHeader
        title="Tài khoản"
        description="Người dùng đăng nhập hai lớp. Thiết bị dùng API key và chỉ ghi được kết quả soi viên."
      />

      {error && (
        <Alert variant="critical">
          <p>{error}</p>
        </Alert>
      )}

      {issuedKey && (
        <Card title={`API key của «${issuedKey.username}»`} variant="caution">
          <Alert variant="caution" icon="key">
            <p>
              Sao chép ngay. Khoá này không hiện lại được; nếu mất thì phải phát khoá mới, và khoá cũ
              hết hiệu lực.
            </p>
          </Alert>
          <CopyRow value={issuedKey.apiKey} />
          <div className="actions">
            <button className="btn secondary" onClick={() => setIssuedKey(null)}>
              Tôi đã lưu
            </button>
          </div>
        </Card>
      )}

      <Card title="Tạo tài khoản">
        <div className="field-grid">
          <Field label="Tên đăng nhập">
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
          </Field>
          <Field label="Vai trò">
            <select
              value={form.role}
              onChange={(e) => setForm({ ...form, role: e.target.value as Role })}
            >
              <option value="admin">Quản trị — tài khoản và mẫu chuẩn</option>
              <option value="operator">Vận hành — mẻ đếm và ghi kết quả</option>
              <option value="viewer">Chỉ xem</option>
              <option value="machine">Thiết bị — dùng API key</option>
            </select>
          </Field>
          {!isMachine && (
            <Field label="Mật khẩu ban đầu" hint={`Tối thiểu ${MIN_PASSWORD_LENGTH} ký tự.`}>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </Field>
          )}
        </div>

        {isMachine && (
          <Alert variant="info" icon="shield">
            <p>
              Tài khoản thiết bị không có mật khẩu và không dùng xác thực hai lớp — thiết bị không gõ
              được mã luân phiên. Đổi lại nó chỉ được ghi kết quả soi viên, không đọc được gì khác.
            </p>
          </Alert>
        )}

        <div className="actions">
          <button
            className="btn"
            onClick={() => void createUser()}
            disabled={!form.username || (!isMachine && form.password.length < MIN_PASSWORD_LENGTH)}
          >
            Tạo tài khoản
          </button>
        </div>
      </Card>

      <section className="card">
        <div className="card-header">
          <h2>Danh sách</h2>
        </div>
        {loading ? (
          <div className="empty">
            <span className="spinner" />
          </div>
        ) : users.length === 0 ? (
          <EmptyState icon="users" title="Chưa có tài khoản nào" />
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Tên</th>
                  <th>Vai trò</th>
                  <th>Lớp thứ hai</th>
                  <th>Trạng thái</th>
                  <th>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {users.map((row) => {
                  const isSelf = row.id === me?.id
                  return (
                    <tr key={row.id}>
                      <td className="cell-strong">
                        {row.username}
                        {isSelf && <span className="hint"> (bạn)</span>}
                      </td>
                      <td>
                        <Badge outline>{ROLE_LABEL[row.role]}</Badge>
                      </td>
                      <td>
                        {row.role === 'machine' ? (
                          <Badge outline icon="key">
                            API key
                          </Badge>
                        ) : row.totp_enabled ? (
                          <Badge status="good" icon="check">
                            Đã bật
                          </Badge>
                        ) : (
                          <Badge status="warning" icon="alert">
                            Chưa ghi danh
                          </Badge>
                        )}
                      </td>
                      <td>
                        {row.is_active ? (
                          <span className="hint">Hoạt động</span>
                        ) : (
                          <Badge status="critical" icon="ban">
                            Đã vô hiệu
                          </Badge>
                        )}
                      </td>
                      <td>
                        <div className="row-actions">
                          {HUMAN_ROLES.includes(row.role) && !isSelf && (
                            <button
                              className="btn secondary sm"
                              onClick={() => void run(() => api.resetTotp(row.id))}
                            >
                              Đặt lại 2FA
                            </button>
                          )}
                          {row.role === 'machine' && (
                            <button
                              className="btn secondary sm"
                              onClick={() =>
                                void run(async () => {
                                  const rotated = await api.rotateApiKey(row.id)
                                  if (rotated.api_key)
                                    setIssuedKey({
                                      username: rotated.username,
                                      apiKey: rotated.api_key,
                                    })
                                })
                              }
                            >
                              Phát key mới
                            </button>
                          )}
                          {!isSelf && (
                            <button
                              className={`btn sm ${row.is_active ? 'danger' : 'secondary'}`}
                              onClick={() =>
                                void run(() =>
                                  api.updateUser(row.id, { is_active: !row.is_active }),
                                )
                              }
                            >
                              {row.is_active ? 'Vô hiệu' : 'Kích hoạt'}
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
