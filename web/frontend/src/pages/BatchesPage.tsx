import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import { Alert, BatchStatusBadge, Card, EmptyState, Field, PageHeader } from '../components/ui'
import { api, type Batch, type Target } from '../lib/api'
import { RoleGate } from '../lib/auth'

export function BatchesPage() {
  const [batches, setBatches] = useState<Batch[]>([])
  const [targets, setTargets] = useState<Target[]>([])
  const [targetId, setTargetId] = useState<number | ''>('')
  const [requestedCount, setRequestedCount] = useState(10)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  async function reload() {
    const [nextBatches, nextTargets] = await Promise.all([api.listBatches(), api.listTargets()])
    setBatches(nextBatches)
    setTargets(nextTargets)
  }

  useEffect(() => {
    reload()
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false))
  }, [])

  async function createBatch() {
    if (targetId === '') return
    try {
      await api.createBatch({ target_id: targetId, requested_count: requestedCount })
      setError(null)
      await reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const targetOf = (batch: Batch) => targets.find((item) => item.id === batch.target_id)

  return (
    <div className="stack">
      <PageHeader
        title="Mẻ đếm"
        description="Mỗi mẻ gắn với một loại viên chuẩn và số viên cần lấy."
      />

      {error && (
        <Alert variant="critical">
          <p>{error}</p>
        </Alert>
      )}

      <RoleGate roles={['admin', 'operator']}>
        <Card title="Tạo mẻ mới">
          <div className="field-grid">
            <Field label="Mẫu chuẩn">
              <select value={targetId} onChange={(e) => setTargetId(Number(e.target.value) || '')}>
                <option value="">— chọn mẫu chuẩn —</option>
                {targets.map((target) => (
                  <option key={target.id} value={target.id}>
                    {target.code} — {target.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Số viên cần lấy">
              <input
                type="number"
                min={1}
                value={requestedCount}
                onChange={(e) => setRequestedCount(Number(e.target.value))}
              />
            </Field>
          </div>
          <div className="actions">
            <button className="btn" onClick={() => void createBatch()} disabled={targetId === ''}>
              Tạo mẻ
            </button>
          </div>
          {targets.length === 0 && (
            <p className="hint">Chưa có mẫu chuẩn nào. Thêm ở trang Mẫu chuẩn trước.</p>
          )}
        </Card>
      </RoleGate>

      <section className="card">
        <div className="card-header">
          <h2>Lịch sử mẻ</h2>
        </div>
        {loading ? (
          <div className="empty">
            <span className="spinner" />
          </div>
        ) : batches.length === 0 ? (
          <EmptyState icon="batches" title="Chưa có mẻ nào">
            Tạo một mẻ để bắt đầu theo dõi tiến độ và số viên từng ô.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Mẻ</th>
                  <th>Mẫu chuẩn</th>
                  <th className="num">Số viên</th>
                  <th>Trạng thái</th>
                  <th>Tạo lúc</th>
                </tr>
              </thead>
              <tbody>
                {batches.map((batch) => (
                  <tr key={batch.id}>
                    <td className="cell-strong">
                      <Link to={`/batches/${batch.id}`}>Mẻ #{batch.id}</Link>
                    </td>
                    <td>{targetOf(batch)?.code ?? `#${batch.target_id}`}</td>
                    <td className="num">{batch.requested_count}</td>
                    <td>
                      <BatchStatusBadge status={batch.status} />
                    </td>
                    <td className="hint">{new Date(batch.created_at).toLocaleString('vi-VN')}</td>
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
