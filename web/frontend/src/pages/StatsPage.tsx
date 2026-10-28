import { useCallback, useEffect, useState } from 'react'

import { Icon } from '../components/Icon'
import { PillChart } from '../components/PillChart'
import { Alert, Card, EmptyState, Field, PageHeader, ROUTE_LOOK, Tile } from '../components/ui'
import { api, type Route, type StatsPeriod, type StatsResponse } from '../lib/api'

const ROUTES: Route[] = ['ACCEPTED', 'DEFECTIVE', 'WRONG_DRUG', 'MULTIPLE_PILLS', 'EMPTY_FRAME']

const PERIODS: { value: StatsPeriod; label: string }[] = [
  { value: 'day', label: 'Ngày' },
  { value: 'week', label: 'Tuần' },
  { value: 'month', label: 'Tháng' },
]

export function StatsPage() {
  const [period, setPeriod] = useState<StatsPeriod>('day')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [data, setData] = useState<StatsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExporting] = useState(false)

  const query = { period, from: from || undefined, to: to || undefined }

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      setData(await api.getStats({ period, from: from || undefined, to: to || undefined }))
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [period, from, to])

  useEffect(() => {
    void reload()
  }, [reload])

  async function exportCsv() {
    setExporting(true)
    try {
      const { blob, filename } = await api.downloadStatsCsv(query)
      save(blob, filename)
      setError(null)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setExporting(false)
    }
  }

  return (
    <div className="stack">
      <PageHeader
        title="Thống kê"
        description="Số viên đã qua máy, gộp theo ngày, tuần hoặc tháng. Mốc thời gian tính theo giờ Việt Nam."
        actions={
          <button
            className="btn"
            onClick={() => void exportCsv()}
            disabled={exporting || loading || !data}
          >
            {exporting ? <span className="spinner sm" /> : <Icon name="download" size={16} />}
            Xuất CSV
          </button>
        }
      />

      {error && (
        <Alert variant="critical">
          <p>{error}</p>
        </Alert>
      )}

      <Card title="Khoảng thời gian">
        <div className="segmented" role="group" aria-label="Gộp theo">
          {PERIODS.map((item) => (
            <button
              key={item.value}
              type="button"
              className={period === item.value ? 'segment active' : 'segment'}
              aria-pressed={period === item.value}
              onClick={() => setPeriod(item.value)}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="field-grid">
          <Field label="Từ ngày">
            <input
              type="date"
              value={from}
              max={to || undefined}
              onChange={(e) => setFrom(e.target.value)}
            />
          </Field>
          <Field label="Đến ngày">
            <input
              type="date"
              value={to}
              min={from || undefined}
              onChange={(e) => setTo(e.target.value)}
            />
          </Field>
        </div>
        <p className="hint">
          Để trống thì lấy khoảng gần nhất: 30 ngày, 12 tuần hoặc 12 tháng.
          {data && ` Đang xem ${formatDay(data.from)} – ${formatDay(data.to)}.`}
        </p>
      </Card>

      {loading && !data ? (
        <div className="empty">
          <span className="spinner" />
        </div>
      ) : data ? (
        <>
          <Card title="Tổng cả khoảng">
            <div className="tiles">
              <Tile label="Viên đạt" value={data.totals.accepted_total} status="good" />
              <Tile
                label="Đã xác nhận rơi"
                value={data.totals.confirmed_total}
                sub="kể cả viên loại"
              />
              <Tile
                label="Camera soi"
                value={data.totals.observed_total}
                sub="kể cả viên bị loại ngay từ ảnh"
              />
              <Tile label="Số mẻ" value={data.totals.batches} />
            </div>
          </Card>

          <Card
            title="Số viên camera soi"
            description="Trục tính theo số lần camera soi, không phải số cảm biến đã xác nhận: trộn hai cơ sở vào một cột sẽ đếm viên đang trên đường rơi thành viên loại."
          >
            {data.totals.observed_total === 0 ? (
              <EmptyState icon="chart" title="Chưa có viên nào trong khoảng này">
                Chọn khoảng khác, hoặc chạy một mẻ để có số liệu.
              </EmptyState>
            ) : (
              <PillChart rows={data.rows} dimmed={loading} />
            )}
          </Card>

          <section className="card">
            <div className="card-header">
              <div>
                <h2>Theo từng {PERIODS.find((item) => item.value === period)?.label.toLowerCase()}</h2>
                <p className="hint">{data.rows.length} kỳ</p>
              </div>
            </div>
            <p className="hint">
              Ba cột <strong>Sai thuốc</strong>, <strong>Nhiều viên</strong> và{' '}
              <strong>Khung trống</strong> là số camera thấy. Máy không bao giờ thả những viên này
              xuống ô nào, nên chúng không có số “đã xác nhận”.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Kỳ</th>
                    <th className="num">Số mẻ</th>
                    <th className="num">Camera soi</th>
                    {ROUTES.map((route) => (
                      <th key={route} className="num">
                        {ROUTE_LOOK[route].label}
                      </th>
                    ))}
                    <th className="num">Đã xác nhận rơi</th>
                    <th className="num">Viên đạt</th>
                  </tr>
                </thead>
                <tbody>
                  {data.rows.map((row) => (
                    <tr key={row.key} className={row.observed_total === 0 ? 'row-quiet' : undefined}>
                      <td className="cell-strong">{row.label}</td>
                      <td className="num">{row.batches}</td>
                      <td className="num">{row.observed_total}</td>
                      {ROUTES.map((route) => (
                        <td key={route} className="num">
                          {row.observed[route] ?? 0}
                        </td>
                      ))}
                      <td className="num">{row.confirmed_total}</td>
                      <td className="num cell-strong">{row.accepted_total}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <td className="cell-strong">Tổng</td>
                    <td className="num">{data.totals.batches}</td>
                    <td className="num">{data.totals.observed_total}</td>
                    {ROUTES.map((route) => (
                      <td key={route} className="num">
                        {data.totals.observed[route] ?? 0}
                      </td>
                    ))}
                    <td className="num">{data.totals.confirmed_total}</td>
                    <td className="num cell-strong">{data.totals.accepted_total}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </div>
  )
}

function formatDay(iso: string): string {
  const [year, month, day] = iso.split('-')
  return `${day}/${month}/${year}`
}

/**
 * Giao file cho trình duyệt. Phải dựng một link tạm rồi thu hồi: endpoint cần
 * header `Authorization`, nên không thể trỏ thẳng `<a href>` vào nó.
 */
function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}
