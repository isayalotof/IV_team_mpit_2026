import { useState } from 'react'
import { ChevronDown, ChevronRight, Download } from 'lucide-react'
import { QueryData } from '@/types'

function downloadCsv(data: QueryData) {
  const escape = (v: unknown) => {
    const s = v == null ? '' : String(v)
    return s.includes(',') || s.includes('"') || s.includes('\n') ? `"${s.replace(/"/g, '""')}"` : s
  }
  const header = data.columns.map((c) => escape(c.name)).join(',')
  const rows = data.rows.map((row) => row.map(escape).join(','))
  const csv = [header, ...rows].join('\r\n')
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `export_${new Date().toISOString().slice(0, 10)}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

interface Props {
  data: QueryData
  defaultOpen?: boolean
}

function formatCell(value: unknown): string {
  if (value == null) return '—'
  if (typeof value === 'number') {
    if (Number.isInteger(value)) return value.toLocaleString('ru-RU')
    return value.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  const str = String(value)
  const num = Number(str)
  if (!isNaN(num) && str.trim() !== '' && !/[a-zA-Zа-яёА-ЯЁ\-]/.test(str)) {
    if (Number.isInteger(num)) return num.toLocaleString('ru-RU')
    return num.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-/i.test(str)) return str.slice(0, 8) + '…'
  return str
}

function isNumericColumn(data: QueryData, colIdx: number): boolean {
  const sample = data.rows.slice(0, 5).map(r => r[colIdx])
  return sample.every(v => v == null || typeof v === 'number' || (!isNaN(Number(v)) && String(v).trim() !== ''))
}

export function DataTable({ data, defaultOpen = true }: Props) {
  const [open, setOpen] = useState(defaultOpen)

  if (!data.columns.length) return null

  const showLimit = 50
  const visibleRows = data.rows.slice(0, showLimit)
  const numericCols = data.columns.map((_, i) => isNumericColumn(data, i))

  return (
    <div style={{ border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-lg)', overflow: 'hidden' }}>
      {/* Header */}
      <div
        style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '10px 14px', background: 'var(--bg-surface)', cursor: 'pointer',
          borderBottom: open ? '1px solid var(--border-subtle)' : 'none',
        }}
        onClick={() => setOpen(!open)}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 12, color: 'var(--text-secondary)' }}>
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          <span style={{ fontWeight: 500 }}>Данные</span>
          <span style={{ color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 11 }}>
            {data.row_count} строк · {data.columns.length} столбцов
          </span>
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); downloadCsv(data) }}
          className="btn sm ghost icon"
          title="Скачать CSV"
          style={{ width: 'auto', padding: '4px 8px', gap: 4 }}
        >
          <Download size={11} />
          <span style={{ fontSize: 10.5 }}>CSV</span>
        </button>
      </div>

      {open && (
        <div style={{ maxHeight: 320, overflowY: 'auto', overflowX: 'auto' }}>
          <table className="data-table">
            <thead style={{ position: 'sticky', top: 0, zIndex: 10, background: 'var(--bg-base)' }}>
              <tr>
                {data.columns.map((col) => (
                  <th key={col.name}>{col.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row, i) => (
                <tr key={i} style={{ background: i % 2 === 0 ? 'var(--bg-base)' : 'var(--bg-surface)' }}>
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className={numericCols[j] ? 'num' : ''}
                      style={{ whiteSpace: 'nowrap' }}
                    >
                      {formatCell(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {data.row_count > showLimit && (
            <div style={{
              padding: '10px 14px', textAlign: 'center', fontSize: 11,
              color: 'var(--text-muted)', background: 'var(--bg-elevated)',
              borderTop: '1px solid var(--border-subtle)', fontFamily: 'var(--font-mono)',
            }}>
              Показано {showLimit} из {data.row_count} строк · Сохраните отчёт для полного результата
            </div>
          )}
        </div>
      )}
    </div>
  )
}
