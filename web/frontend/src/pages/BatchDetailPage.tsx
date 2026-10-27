import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Icon } from '../components/Icon'
import {
  Alert,
  BatchStatusBadge,
  Card,
  EmptyState,
  Meter,
  PageHeader,
  ROUTE_LOOK,
  RouteBadge,
  Tile,
} from '../components/ui'
import { api, type BatchDetail, type BatchStatus, type PillEvent, type Route } from '../lib/api'
import { RoleGate, useAuth } from '../lib/auth'

const ROUTES: Route[] = ['ACCEPTED', 'DEFECTIVE', 'WRONG_DRUG', 'MULTIPLE_PILLS', 'EMPTY_FRAME']

const STATUS_ACTIONS: { status: BatchStatus; label: string; variant?: string }[] = [
  { status: 'running', label: 'Bắt đầu' },
  { status: 'paused', label: 'Tạm dừng', variant: 'secondary' },
  { status: 'done', label: 'Kết thúc', variant: 'secondary' },
  { status: 'aborted', label: 'Huỷ mẻ', variant: 'danger' },
]

export function BatchDetailPage() {
  const { can } = useAuth()
  const { batchId } = useParams()
  const id = Number(batchId)
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [events, setEvents] = useState<PillEvent[]>([])
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    const [nextBatch, nextEvents] = await Promise.all([api.getBatch(id), api.listEvents(id)])
    setBatch(nextBatch)
    setEvents(nextEvents)
  }, [id])

  useEffect(() => {
    reload().catch((err: Error) => setError(err.message))
  }, [reload])

  async function run(action: () => Promise<unknown>) {
    try {
      await action()
      setError(null)
      await reload()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (!batch) {
    return error ? (
      <Alert variant="critical">
        <p>{error}</p>
      </Alert>
    ) : (
      <div className="empty">
        <span className="spinner" />
      </div>
    )
  }

  const canOperate = can('admin', 'operator')

  return (
    <div className="stack">
      <PageHeader
        title={`Mẻ #${batch.id}`}
        description={`Cần lấy ${batch.requested_count} viên · tạo ${new Date(
          batch.created_at,
        ).toLocaleString('vi-VN')}`}
        actions={<BatchStatusBadge status={batch.status} />}
      />

      <p>
        <Link to="/batches" className="hint">
          ← Về danh sách mẻ
        </Link>
      </p>

      {error && (
        <Alert variant="critical">
          <p>{error}</p>
        </Alert>
      )}

      <RoleGate roles={['admin', 'operator']}>
        <div className="actions">
          {STATUS_ACTIONS.map((action) => (
            <button
              key={action.status}
              className={`btn ${action.variant ?? ''}`}
              disabled={batch.status === action.status}
              onClick={() => void run(() => api.setBatchStatus(id, action.status))}
            >
              {action.label}
            </button>
          ))}
        </div>
      </RoleGate>

      <Card
        title="Bộ đếm của mẻ"
        description="Chỉ tính những viên mà cảm biến đường rơi đã xác nhận vào ô."
      >
        <Meter
          value={batch.counters.confirmed_total}
          max={batch.requested_count}
          caption="Tiến độ mẻ"
          rightCaption={`${batch.counters.confirmed_total} / ${batch.requested_count} viên`}
        />

        <div className="tiles">
          {ROUTES.map((route) => {
            const look = ROUTE_LOOK[route]
            const confirmed = batch.counters.confirmed[route]
            const observed = batch.counters.observed[route]
            return (
              <Tile
                key={route}
                label={look.label}
                value={confirmed}
                status={look.status}
                sub={`camera thấy ${observed}`}
                dim={confirmed === 0}
              />
            )
          })}
        </div>

        <p className="hint">
          Con số lớn là <strong>đã xác nhận</strong> — bộ đếm chính thức. Dòng dưới là{' '}
          <strong>camera thấy</strong>, tức kết luận của ảnh trước khi cảm biến báo viên đã rơi. Hai
          số lệch nhau là bình thường khi hệ thống chưa được phép thả viên.
        </p>
      </Card>

      <section className="card">
        <div className="card-header">
          <div>
            <h2>Từng viên</h2>
            <p className="hint">{events.length} lần soi</p>
          </div>
        </div>
        {events.length === 0 ? (
          <EmptyState icon="pill" title="Chưa có viên nào được ghi nhận">
            Thiết bị sẽ đẩy kết quả soi từng viên vào đây khi mẻ đang chạy.
          </EmptyState>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th className="num">#</th>
                  <th>Kết quả</th>
                  <th>Lý do</th>
                  <th>Cảm biến rơi</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td className="num">{event.sequence}</td>
                    <td>
                      <RouteBadge route={event.route} />
                    </td>
                    <td className="cell-reason">{event.reason}</td>
                    <td>
                      {event.drop_confirmed ? (
                        <span className="inline hint">
                          <Icon name="check" size={14} />
                          đã xác nhận
                        </span>
                      ) : (
                        <button
                          className="btn secondary sm"
                          disabled={!event.release_allowed || !canOperate}
                          title={
                            event.release_allowed
                              ? undefined
                              : 'Viên này chưa được phép thả, nên không thể xác nhận đã rơi'
                          }
                          onClick={() => void run(() => api.confirmDrop(id, event.id, true))}
                        >
                          Xác nhận rơi
                        </button>
                      )}
                    </td>
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
