import { useEffect, useState } from 'react'

import { Alert, Card, EmptyState, Field, PageHeader } from '../components/ui'
import { api, type Target } from '../lib/api'
import { RoleGate } from '../lib/auth'

const EMPTY_FORM = { code: '', name: '', recognition_label: '', note: '' }

export function TargetsPage() {
  const [targets, setTargets] = useState<Target[]>([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function reload() {
    setTargets(await api.listTargets())
  }

  useEffect(() => {
    reload()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function submit() {
    try {
      await api.createTarget({
        code: form.code,
        name: form.name,
        recognition_label: form.recognition_label || null,
        note: form.note || null,
      })
      setForm(EMPTY_FORM)
      setError(null)
      await reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="stack">
      <PageHeader
        title="Mẫu chuẩn"
        description="Loại viên mà một mẻ đếm đối chiếu từng viên với nó."
      />

      {error && (
        <Alert variant="critical">
          <p>{error}</p>
        </Alert>
      )}

      <RoleGate roles={['admin']}>
        <Card title="Thêm mẫu chuẩn">
          <div className="field-grid">
            <Field label="Mã">
              <input
                value={form.code}
                placeholder="KEO-TRANG-TRON"
                onChange={(e) => setForm({ ...form, code: e.target.value })}
              />
            </Field>
            <Field label="Tên">
              <input
                value={form.name}
                placeholder="Viên mô phỏng trắng tròn"
                onChange={(e) => setForm({ ...form, name: e.target.value })}
              />
            </Field>
            <Field
              label="Nhãn nhận diện của nhánh AI"
              hint="ID ảnh của bộ dữ liệu, không xác nhận hoạt chất hay thuốc thật."
            >
              <input
                value={form.recognition_label}
                placeholder="ví dụ 64"
                onChange={(e) => setForm({ ...form, recognition_label: e.target.value })}
              />
            </Field>
            <Field label="Ghi chú">
              <input
                value={form.note}
                onChange={(e) => setForm({ ...form, note: e.target.value })}
              />
            </Field>
          </div>
          <div className="actions">
            <button className="btn" onClick={() => void submit()} disabled={!form.code || !form.name}>
              Thêm mẫu chuẩn
            </button>
          </div>
        </Card>
      </RoleGate>

      <section className="card">
        <div className="card-header">
          <h2>Danh sách</h2>
        </div>
        {loading ? (
          <div className="empty">
            <span className="spinner" />
          </div>
        ) : targets.length === 0 ? (
          <EmptyState icon="targets" title="Chưa có mẫu chuẩn nào">
            Quản trị viên thêm mẫu chuẩn trước khi vận hành tạo mẻ đếm.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mã</th>
                  <th>Tên</th>
                  <th>Nhãn AI</th>
                  <th>Ghi chú</th>
                </tr>
              </thead>
              <tbody>
                {targets.map((target) => (
                  <tr key={target.id}>
                    <td className="cell-strong">{target.code}</td>
                    <td>{target.name}</td>
                    <td className="nums">{target.recognition_label ?? '—'}</td>
                    <td className="cell-reason">{target.note ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
