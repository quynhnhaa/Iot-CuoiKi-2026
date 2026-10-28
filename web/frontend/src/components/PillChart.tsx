import { useEffect, useId, useRef, useState } from 'react'

import { ROUTE_LOOK } from './ui'
import type { Route, StatsRow } from '../lib/api'

/**
 * Cột chồng: mỗi kỳ một cột, chia hai khúc — viên camera kết luận “đúng,
 * nguyên” và phần còn lại bị loại.
 *
 * **Hai khúc chứ không phải năm.** Năm đường vốn đã có sẵn màu trạng thái, nên
 * vẽ cả năm là chuyện dễ nghĩ nhất. Nhưng chạy bộ màu đó qua công cụ kiểm thì
 * cặp “Sứt, vỡ” (#fab219) và “Nhiều viên” (#ec835a) chỉ cách nhau ΔE 13,6 —
 * dưới ngưỡng 15, nghĩa là **người mắt thường cũng khó phân biệt** khi hai khúc
 * nằm sát nhau, chưa nói tới người mù màu; màu vàng còn chỉ đạt 1,79:1 so với
 * nền sáng.
 *
 * Nên biểu đồ chỉ trả lời câu hỏi mà bảng bên dưới trả lời chậm: *sản lượng lên
 * hay xuống, tỷ lệ loại có tăng không*. Chi tiết năm đường vẫn còn nguyên trong
 * chú thích khi trỏ vào và trong bảng. Cặp xanh lá + xám đã qua kiểm ở cả nền
 * sáng lẫn nền tối: tương phản ≥ 3:1, ΔE người mắt thường 21,7, mù màu 11,1.
 *
 * Trục tính theo **số camera soi**, không phải số cảm biến đã xác nhận. Trộn
 * hai cơ sở đó vào một cột sẽ khiến viên đang trên đường rơi bị đếm thành viên
 * loại. Số đã xác nhận nằm ở ô tổng phía trên và ở bảng.
 */

const PLOT_H = 190
const MARGIN = { top: 14, right: 12, bottom: 30, left: 48 }
const SLOT_MIN = 28
const SLOT_MAX = 72
const NOMINAL_WIDTH = 880
const BAR_MAX = 24
// Khe hở bằng màu nền, không phải đường viền: viền là mực thừa không mang dữ liệu.
const GAP = 2
// Nửa bề rộng hộp chú thích; xem `.chart-tip` trong components.css.
const TIP_HALF = 104

const REJECT_ROUTES: Route[] = ['DEFECTIVE', 'WRONG_DRUG', 'MULTIPLE_PILLS', 'EMPTY_FRAME']

export function PillChart({ rows, dimmed }: { rows: StatsRow[]; dimmed?: boolean }) {
  const titleId = useId()
  const [hovered, setHovered] = useState<number | null>(null)

  // Hộp chú thích nằm **ngoài** vùng cuộn, vì `overflow-x: auto` kéo theo
  // `overflow-y: auto` — đặt nó bên trong thì đáy hộp bị cắt cụt. Đổi lại, nó
  // phải tự bù bề rộng khung nhìn và vị trí đã cuộn.
  const scrollRef = useRef<HTMLDivElement>(null)
  const [view, setView] = useState({ width: 0, left: 0 })

  useEffect(() => {
    const node = scrollRef.current
    if (!node) return
    const measure = () => setView((old) => ({ ...old, width: node.clientWidth }))
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const slot = Math.max(SLOT_MIN, Math.min(SLOT_MAX, NOMINAL_WIDTH / Math.max(rows.length, 1)))
  const width = MARGIN.left + MARGIN.right + slot * rows.length
  const height = MARGIN.top + PLOT_H + MARGIN.bottom
  const baseY = MARGIN.top + PLOT_H

  const peak = Math.max(...rows.map((row) => row.observed_total), 0)
  const ticks = tickValues(peak)
  const top = ticks[ticks.length - 1]
  const scale = (value: number) => (top === 0 ? 0 : (value / top) * PLOT_H)

  // Nhãn trục ngang thưa dần theo số kỳ: 30 nhãn chồng lên nhau thì không đọc
  // được nhãn nào.
  const labelEvery = Math.ceil(rows.length / 8)
  const barWidth = Math.min(BAR_MAX, slot - 6)
  const active = hovered === null ? null : rows[hovered]

  // Ghim hộp vào trong khung nhìn: ở cột đầu và cột cuối, hộp canh giữa sẽ thò
  // ra ngoài và bị cắt mất một nửa.
  const visible = view.width || width
  const tipLeft =
    hovered === null
      ? 0
      : Math.min(
          Math.max(MARGIN.left + (hovered + 0.5) * slot - view.left, TIP_HALF),
          Math.max(visible - TIP_HALF, TIP_HALF),
        )

  return (
    <div className="chart" style={dimmed ? { opacity: 0.55 } : undefined}>
      <div className="chart-legend">
        <span className="legend-item">
          <span className="legend-swatch good" />
          Đúng, nguyên
        </span>
        <span className="legend-item">
          <span className="legend-swatch rest" />
          Bị loại
        </span>
      </div>

      <div className="chart-frame">
        <div
          className="chart-scroll"
          ref={scrollRef}
          onScroll={(event) => setView((old) => ({ ...old, left: event.currentTarget.scrollLeft }))}
        >
          <svg
            width={width}
            height={height}
            role="img"
            aria-labelledby={titleId}
            onPointerLeave={() => setHovered(null)}
          >
            <title id={titleId}>
              {`Số viên camera soi theo từng kỳ, chia thành viên đúng nguyên và viên bị loại.`}
              {` Cao nhất ${peak} viên. Số liệu đầy đủ nằm ở bảng bên dưới.`}
            </title>

            {ticks.map((tick) => {
              const y = baseY - scale(tick)
              return (
                <g key={tick} aria-hidden="true">
                  <line x1={MARGIN.left} x2={width - MARGIN.right} y1={y} y2={y} className="grid" />
                  <text x={MARGIN.left - 8} y={y + 4} textAnchor="end" className="axis nums">
                    {tick}
                  </text>
                </g>
              )
            })}

            {rows.map((row, index) => {
              const slotX = MARGIN.left + index * slot
              const x = slotX + (slot - barWidth) / 2
              const accepted = row.observed.ACCEPTED ?? 0
              const rejected = row.observed_total - accepted
              return (
                <g key={row.key}>
                  <Column
                    x={x}
                    baseY={baseY}
                    width={barWidth}
                    accepted={scale(accepted)}
                    rejected={scale(rejected)}
                    faded={hovered !== null && hovered !== index}
                  />
                  {index % labelEvery === 0 && (
                    <text
                      x={slotX + slot / 2}
                      y={baseY + 20}
                      textAnchor="middle"
                      className="axis"
                      aria-hidden="true"
                    >
                      {shortLabel(row)}
                    </text>
                  )}
                  {/* Vùng bắt chuột rộng cả ô, không chỉ phần cột đã tô: một
                      cột 2px không ai trỏ trúng. Cũng nhận được tiêu điểm bàn
                      phím, để người không dùng chuột đọc được đúng nội dung đó. */}
                  <rect
                    x={slotX}
                    y={MARGIN.top}
                    width={slot}
                    height={PLOT_H}
                    fill="transparent"
                    tabIndex={0}
                    className="chart-hit"
                    aria-label={describe(row)}
                    onPointerEnter={() => setHovered(index)}
                    onFocus={() => setHovered(index)}
                    onBlur={() => setHovered(null)}
                  />
                </g>
              )
            })}

            <line
              x1={MARGIN.left}
              x2={width - MARGIN.right}
              y1={baseY}
              y2={baseY}
              className="axis-rule"
              aria-hidden="true"
            />
          </svg>
        </div>

        {active && (
          <div className="chart-tip" style={{ left: tipLeft }} role="presentation">
            <p className="chart-tip-title">{active.label}</p>
            <p className="chart-tip-lead">
              <strong className="nums">{active.observed_total}</strong> viên camera soi
            </p>
            <ul>
              <li>
                <span className="legend-key good" />
                <strong className="nums">{active.observed.ACCEPTED ?? 0}</strong>
                <span>Đúng, nguyên</span>
              </li>
              {REJECT_ROUTES.map((route) => (
                <li key={route}>
                  <span className="legend-key rest" />
                  <strong className="nums">{active.observed[route] ?? 0}</strong>
                  <span>{ROUTE_LOOK[route].label}</span>
                </li>
              ))}
            </ul>
            <p className="chart-tip-foot">
              {active.batches} mẻ · {active.accepted_total} viên đạt đã xác nhận
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

/**
 * Một cột. Khúc dưới vuông đáy vì nó mọc từ đường gốc; chỉ đầu trên cùng của cả
 * cột mới bo 4px.
 */
function Column({
  x,
  baseY,
  width,
  accepted,
  rejected,
  faded,
}: {
  x: number
  baseY: number
  width: number
  accepted: number
  rejected: number
  faded: boolean
}) {
  const className = faded ? 'bar faded' : 'bar'
  if (accepted <= 0 && rejected <= 0) return null

  if (rejected <= 0) {
    return (
      <path d={cappedBar(x, baseY - accepted, width, accepted)} className={`${className} good`} />
    )
  }
  if (accepted <= 0) {
    return (
      <path d={cappedBar(x, baseY - rejected, width, rejected)} className={`${className} rest`} />
    )
  }

  // Khe hở lấy từ khúc trên, không cộng thêm vào cột: cộng thêm thì cột cao hơn
  // giá trị thật của nó.
  const topHeight = Math.max(rejected - GAP, 1)
  const topY = baseY - accepted - GAP - topHeight
  return (
    <>
      <rect
        x={x}
        y={baseY - accepted}
        width={width}
        height={accepted}
        className={`${className} good`}
      />
      <path d={cappedBar(x, topY, width, topHeight)} className={`${className} rest`} />
    </>
  )
}

/** Hình chữ nhật bo 4px hai góc trên, vuông hai góc dưới. */
function cappedBar(x: number, y: number, width: number, height: number): string {
  const r = Math.min(4, width / 2, height)
  return [
    `M ${x} ${y + height}`,
    `L ${x} ${y + r}`,
    `A ${r} ${r} 0 0 1 ${x + r} ${y}`,
    `L ${x + width - r} ${y}`,
    `A ${r} ${r} 0 0 1 ${x + width} ${y + r}`,
    `L ${x + width} ${y + height}`,
    'Z',
  ].join(' ')
}

/** Mốc trục dọc làm tròn: 0 và các bậc chẵn lên tới trên giá trị cao nhất. */
function tickValues(peak: number): number[] {
  if (peak <= 0) return [0, 1]
  const rough = peak / 4
  const magnitude = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 5, 10].map((n) => n * magnitude).find((n) => n >= rough) ?? magnitude * 10
  const ticks: number[] = []
  for (let value = 0; value < peak + step; value += step) ticks.push(value)
  return ticks
}

/** Nhãn trục ngang: ngày và tháng là đủ, năm đã có trong phần chọn khoảng. */
function shortLabel(row: StatsRow): string {
  const [, month, day] = row.key.split('-')
  return row.label.startsWith('Tháng') ? `T${Number(month)}` : `${day}/${month}`
}

function describe(row: StatsRow): string {
  const accepted = row.observed.ACCEPTED ?? 0
  return `${row.label}: ${row.observed_total} viên camera soi, ${accepted} đúng nguyên, ${
    row.observed_total - accepted
  } bị loại.`
}
