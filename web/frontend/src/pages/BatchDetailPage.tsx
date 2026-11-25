import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Alert, Badge, BatchStatusBadge, Card, EmptyState, PageHeader, RouteBadge, Tile } from '../components/ui'
import { api, type BatchDetail, type BatchStatus, type PillEvent, type Target, type TrayCount, type TrayResult } from '../lib/api'
import { RoleGate } from '../lib/auth'

const TRAYS = [1, 2, 3] as const
const STATUS_ACTIONS: { status: BatchStatus; label: string; variant?: string }[] = [
  { status: 'running', label: 'Bắt đầu' },
  { status: 'paused', label: 'Tạm dừng', variant: 'secondary' },
  { status: 'done', label: 'Kết thúc', variant: 'secondary' },
  { status: 'aborted', label: 'Huỷ mẻ', variant: 'danger' },
]
const ALLOWED_TRANSITIONS: Record<BatchStatus, BatchStatus[]> = {
  pending: ['running', 'aborted'], running: ['paused', 'done', 'aborted'], paused: ['running', 'done', 'aborted'], done: [], aborted: [],
}

type TraySummary = { correct: number; wrong: number; broken: number; total: number }

function normalized(value: string) {
  return value.trim().normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('vi-VN')
}

function isBroken(label: string) {
  return ['broken', 'defective', 'cracked', 'vien be', 'sut vo', 'be vo'].includes(normalized(label))
}

function summarizeTray(counts: TrayCount[], target: Target | null): TraySummary {
  const acceptedLabels = target
    ? [target.recognition_label, target.code, target.name].filter((label): label is string => Boolean(label)).map(normalized)
    : []
  return counts.reduce<TraySummary>((summary, item) => {
    summary.total += item.count
    if (isBroken(item.label)) summary.broken += item.count
    else if (acceptedLabels.includes(normalized(item.label))) summary.correct += item.count
    else summary.wrong += item.count
    return summary
  }, { correct: 0, wrong: 0, broken: 0, total: 0 })
}

function countLabel(counts: TrayCount[]) {
  return counts.map((item) => `${item.label}: ${item.count}`).join(' · ')
}

export function BatchDetailPage() {
  const { batchId } = useParams()
  const id = Number(batchId)
  const [batch, setBatch] = useState<BatchDetail | null>(null)
  const [events, setEvents] = useState<PillEvent[]>([])
  const [trayResults, setTrayResults] = useState<TrayResult[]>([])
  const [target, setTarget] = useState<Target | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedTray, setSelectedTray] = useState<'all' | number>('all')
  const reload = useCallback(async () => {
    const [nextBatch, nextEvents, nextTrayResults, targets] = await Promise.all([
      api.getBatch(id), api.listEvents(id), api.listTrayResults(id), api.listTargets(),
    ])
    setBatch(nextBatch)
    setEvents(nextEvents)
    setTrayResults(nextTrayResults)
    setTarget(targets.find((item) => item.id === nextBatch.target_id) ?? null)
  }, [id])

  useEffect(() => { reload().catch((err: Error) => setError(err.message)) }, [reload])
  async function run(action: () => Promise<unknown>) {
    try { await action(); setError(null); await reload() } catch (err) { setError((err as Error).message) }
  }
  if (!batch) return error ? <Alert variant="critical"><p>{error}</p></Alert> : <div className="empty"><span className="spinner" /></div>

  const visibleEvents = events.filter(
    (event) => event.route !== 'EMPTY_FRAME' && event.route !== 'MULTIPLE_PILLS',
  )
  const filteredEvents = selectedTray === 'all'
    ? visibleEvents
    : visibleEvents.filter((event) => event.tray_number === selectedTray)
  const summaries = TRAYS.map((tray) => summarizeTray(
    trayResults.find((result) => result.tray_number === tray)?.counts ?? [], target,
  ))
  const overall = summaries.reduce<TraySummary>((total, summary) => ({
    correct: total.correct + summary.correct,
    wrong: total.wrong + summary.wrong,
    broken: total.broken + summary.broken,
    total: total.total + summary.total,
  }), { correct: 0, wrong: 0, broken: 0, total: 0 })
  return (
    <div className="stack">
      <PageHeader title={`Mẻ #${batch.id}`} description={`Tạo ${new Date(batch.created_at).toLocaleString('vi-VN')}`} actions={<BatchStatusBadge status={batch.status} />} />
      <p><Link to="/batches" className="hint">← Về danh sách mẻ</Link></p>
      {error && <Alert variant="critical"><p>{error}</p></Alert>}
      <RoleGate roles={['admin', 'operator']}><div className="actions">{STATUS_ACTIONS.map((action) => (
        <button key={action.status} className={`btn ${action.variant ?? ''}`} disabled={!ALLOWED_TRANSITIONS[batch.status].includes(action.status)} onClick={() => void run(() => api.setBatchStatus(id, action.status))}>{action.label}</button>
      ))}</div></RoleGate>

      <Card title="Thông tin mẻ"><dl className="meta-grid">
        <div><dt>Mẫu chuẩn</dt><dd>{target ? `${target.code} — ${target.name}` : `#${batch.target_id}`}</dd></div>
        <div><dt>Người vận hành</dt><dd>{batch.operator ?? '—'}</dd></div>
        <div><dt>Bắt đầu</dt><dd>{batch.started_at ? new Date(batch.started_at).toLocaleString('vi-VN') : 'chưa chạy'}</dd></div>
        <div><dt>Kết thúc</dt><dd>{batch.finished_at ? new Date(batch.finished_at).toLocaleString('vi-VN') : '—'}</dd></div>
      </dl>{batch.note && <p className="hint">{batch.note}</p>}</Card>

      <Card title="Tổng hợp kết quả AI" description="Web đối chiếu nhãn AI với mẫu thuốc đã chọn của mẻ; không dùng kết luận đúng/sai từ AI.">
        <p className="headline-count"><strong>{overall.total}</strong> viên đã nhận diện <span className="hint">· 3 khay</span></p>
        <div className="tiles">
          <Tile label="Đúng thuốc" value={overall.correct} status="good" sub="viên" dim={overall.correct === 0} />
          <Tile label="Sai thuốc" value={overall.wrong} status="critical" sub="viên" dim={overall.wrong === 0} />
          <Tile label="Viên bể" value={overall.broken} status="warning" sub="viên" dim={overall.broken === 0} />
        </div>
      </Card>

      <Card title="Kết quả theo khay" description="Mỗi khay hiển thị số viên đúng thuốc, sai thuốc và viên bể từ snapshot AI mới nhất.">
        <div className="tray-results">{TRAYS.map((tray, index) => {
          const result = trayResults.find((item) => item.tray_number === tray)
          const summary = summaries[index]
          return <article className="tray-result" key={tray}>
            <div className="tray-result-header"><h3>Khay {tray}</h3>{result ? <Badge status="neutral">{summary.total} viên</Badge> : <span className="hint">Chưa có kết quả</span>}</div>
            {result ? <>
              <div className="tray-statuses">
                <span className="tray-status good">Đúng: <strong>{summary.correct}</strong></span>
                <span className="tray-status critical">Sai: <strong>{summary.wrong}</strong></span>
                <span className="tray-status warning">Bể: <strong>{summary.broken}</strong></span>
              </div>
              <p className="hint tray-count-labels">{countLabel(result.counts)}</p>
            </> : <p className="hint">AI chưa gửi số lượng cho khay này.</p>}
          </article>
        })}</div>
      </Card>

      <Card title="Ảnh theo khay" description="Mỗi mẻ có ba khay; ảnh gần nhất của từng khay được hiển thị tại đây.">
        <div className="tray-images">{TRAYS.map((tray) => {
          const trayResult = trayResults.find((result) => result.tray_number === tray)
          const trayEvent = visibleEvents.find((event) => event.tray_number === tray)
          return <article className="tray-image" key={tray}>
            <div className="tray-image-header"><h3>Khay {tray}</h3><span className="hint">{trayResult?.image_path || trayEvent?.image_path ? 'Đã nhận ảnh' : 'Chưa nhận ảnh'}</span></div>
            {trayResult?.image_path || trayEvent?.image_path ? <img src={trayResult?.image_path ?? trayEvent?.image_path ?? ''} alt={`Ảnh soi của khay ${tray}`} /> : <div className="tray-image-empty">Chưa có ảnh cho khay này</div>}
          </article>
        })}</div>
      </Card>

      <section className="card"><div className="card-header">
        <div><h2>Từng viên</h2><p className="hint">{filteredEvents.length} / {visibleEvents.length} viên</p></div>
        <label className="table-filter"><span>Khay</span><select value={selectedTray} onChange={(event) => setSelectedTray(event.target.value === 'all' ? 'all' : Number(event.target.value))}>
          <option value="all">Tất cả khay</option>{TRAYS.map((tray) => <option key={tray} value={tray}>Khay {tray}</option>)}
        </select></label>
      </div>
      {visibleEvents.length === 0 ? <EmptyState icon="pill" title="Chưa có viên nào được ghi nhận">Thiết bị sẽ đẩy kết quả soi từng viên vào đây khi mẻ đang chạy.</EmptyState>
        : filteredEvents.length === 0 ? <EmptyState icon="inbox" title="Khay này chưa có lần soi nào">Chọn khay khác hoặc xem tất cả khay.</EmptyState>
        : <div className="table-wrap"><table><thead><tr><th className="num">#</th><th>Lúc</th><th>Khay</th><th>Kết quả</th><th>Lý do</th></tr></thead><tbody>
          {filteredEvents.map((event) => <tr key={event.id}><td className="num">{event.sequence}</td><td className="hint">{new Date(event.created_at).toLocaleTimeString('vi-VN')}</td><td>{event.tray_number ? `Khay ${event.tray_number}` : 'Chưa gán khay'}</td><td><RouteBadge route={event.route} /></td><td className="cell-reason">{event.reason}</td></tr>)}
        </tbody></table></div>}
      </section>
    </div>
  )
}
