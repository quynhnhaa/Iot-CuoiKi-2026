import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'

import { Icon } from '../components/Icon'
import {
  Alert,
  BatchStatusBadge,
  Card,
  EmptyState,
  PageHeader,
  ROUTE_LOOK,
  RouteBadge,
  Tile,
} from '../components/ui'
import {
  api,
  type BatchDetail,
  type BatchStatus,
  type PillEvent,
  type Route,
  type Target,
} from '../lib/api'
import { RoleGate, useAuth } from '../lib/auth'

const ROUTES: Route[] = ['ACCEPTED', 'DEFECTIVE', 'WRONG_DRUG', 'MULTIPLE_PILLS', 'EMPTY_FRAME']

const STATUS_ACTIONS: { status: BatchStatus; label: string; variant?: string }[] = [
  { status: 'running', label: 'Bắt đầu' },
  { status: 'paused', label: 'Tạm dừng', variant: 'secondary' },
  { status: 'done', label: 'Kết thúc', variant: 'secondary' },
  { status: 'aborted', label: 'Huỷ mẻ', variant: 'danger' },
]

/**
 * Bản sao của bảng chuyển trạng thái trong `app/services/batch_state.py`.
 * Backend vẫn là nơi quyết định — nó trả 409 cho bước không hợp lệ. Bảng ở
 * đây chỉ để không mời người dùng bấm một nút chắc chắn hỏng; mẻ đã xong hoặc
 * đã huỷ thì không đi đâu được nữa.
 */
const ALLOWED_TRANSITIONS: Record<BatchStatus, BatchStatus[]> = {
  pending: ['running', 'aborted'],
  running: ['paused', 'done', 'aborted'],
  paused: ['running', 'done', 'aborted'],
  done: [],
  aborted: [],
}

export function BatchDetailPage() {
  const { can } = useAuth()
  const { batchId } = useParams()
  const id = Number(batchId)
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [events, setEvents] = useState<PillEvent[]>([])
  const [target, setTarget] = useState<Target | null>(null)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    const [nextBatch, nextEvents, targets] = await Promise.all([
      api.getBatch(id),
      api.listEvents(id),
      api.listTargets(),
    ])
    setBatch(nextBatch)
    setEvents(nextEvents)
    setTarget(targets.find((item) => item.id === nextBatch.target_id) ?? null)
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
        description={`Tạo ${new Date(batch.created_at).toLocaleString('vi-VN')}`}
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
              disabled={!ALLOWED_TRANSITIONS[batch.status].includes(action.status)}
              onClick={() => void run(() => api.setBatchStatus(id, action.status))}
            >
              {action.label}
            </button>
          ))}
        </div>
      </RoleGate>

      <Card title="Thông tin mẻ">
        <dl className="meta-grid">
          <div>
            <dt>Mẫu chuẩn</dt>
            <dd>{target ? `${target.code} — ${target.name}` : `#${batch.target_id}`}</dd>
          </div>
          <div>
            <dt>Người vận hành</dt>
            <dd>{batch.operator ?? '—'}</dd>
          </div>
          <div>
            <dt>Bắt đầu</dt>
            <dd>
              {batch.started_at ? new Date(batch.started_at).toLocaleString('vi-VN') : 'chưa chạy'}
            </dd>
          </div>
          <div>
            <dt>Kết thúc</dt>
            <dd>
              {batch.finished_at ? new Date(batch.finished_at).toLocaleString('vi-VN') : '—'}
            </dd>
          </div>
        </dl>
        {batch.note && <p className="hint">{batch.note}</p>}
      </Card>

      <Card
        title="Bộ đếm của mẻ"
        description="Viên được phép thả thì đếm theo cảm biến; viên bị loại ngay từ ảnh thì đếm theo camera."
      >
        <p className="headline-count">
          <strong>{batch.counters.accepted_total}</strong> viên đạt đã đếm được
          <span className="hint"> · {batch.counters.confirmed_total} viên đã rơi có xác nhận</span>
        </p>

        <div className="tiles">
          {ROUTES.map((route) => {
            const look = ROUTE_LOOK[route]
            const confirmed = batch.counters.confirmed[route]
            const observed = batch.counters.observed[route]
            // Ba nhãn không bao giờ được phép thả thì không có gì để cảm biến
            // xác nhận, nên số "đã xác nhận" của chúng vĩnh viễn bằng 0. Đưa
            // số 0 đó lên chỗ to nhất là nói sai: ô "Sai thuốc" sẽ báo 0 trong
            // khi camera vừa bắt được một viên sai. Với ba nhãn đó, số camera
            // thấy mới là con số có nghĩa.
            const value = look.droppable ? confirmed : observed
            return (
              <Tile
                key={route}
                label={look.label}
                value={value}
                status={look.status}
                sub={look.droppable ? `camera thấy ${observed}` : 'camera thấy · không thả'}
                dim={value === 0}
              />
            )
          })}
        </div>

        <p className="hint">
          Mẻ đếm đến khi người vận hành bấm kết thúc. Viên sứt vỡ cũng rơi và cũng được cảm biến
          xác nhận, nhưng rơi vào ô loại nên không tính là một viên đã lấy được.
        </p>

        <p className="hint">
          Hai ô đầu đếm số viên <strong>cảm biến đường rơi đã xác nhận</strong>; dòng dưới là số
          camera thấy, và hai số lệch nhau nghĩa là có viên đang trên đường rơi — hoặc đang kẹt.
        </p>

        <p className="hint">
          Ba ô sau đếm <strong>số camera thấy</strong>. Máy không bao giờ thả những viên này xuống
          ô nào, nên cảm biến không có gì để xác nhận và một bộ đếm “đã xác nhận” cho chúng sẽ mãi
          bằng 0.
        </p>
      </Card>

      <section className="card">
        <div className="card-header">
          <div>
            <h2>Từng viên</h2>
            <p className="hint">{events.length} lần soi</p>
          </div>
        </div>
        <p className="hint">
          Ô ảnh là khung chỗ cho ảnh camera soi từng viên. Thiết bị gửi được đường dẫn ảnh
          (`image_path`), nhưng web chưa nhận ảnh trực tiếp từ camera nên khung còn trống.
        </p>
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
                  <th>Lúc</th>
                  <th>Ảnh</th>
                  <th>Kết quả</th>
                  <th>Lý do</th>
                  <th>Cảm biến rơi</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.id}>
                    <td className="num">{event.sequence}</td>
                    <td className="hint">
                      {new Date(event.created_at).toLocaleTimeString('vi-VN')}
                    </td>
                    <td>
                      <PillThumb path={event.image_path} />
                    </td>
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


/**
 * Khung ảnh của một viên. Chưa có đường nhận ảnh từ camera nên khung luôn
 * trống — để đó cho thấy chỗ của ảnh, và để không ai tưởng là đã có ảnh mà
 * giao diện quên hiện.
 */
function PillThumb({ path }: { path: string | null }) {
  return (
    <span
      className={path ? 'thumb has-path' : 'thumb'}
      title={path ? `Thiết bị ghi đường dẫn: ${path}` : 'Chưa nhận ảnh từ camera'}
      aria-label={path ? 'Có đường dẫn ảnh, chưa tải được ảnh' : 'Chưa có ảnh'}
    >
      <Icon name="camera" size={18} />
    </span>
  )
}
