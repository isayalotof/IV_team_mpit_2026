import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Play, Eye, Trash2, Calendar, Plus, Download } from 'lucide-react'
import { listReports, deleteReport, runReport } from '@/api/reports'
import { exportReportPdf } from '@/api/dashboards'
import { Report, QueryData, ChartConfig } from '@/types'
import { formatDate } from '@/lib/utils'
import { ResultChart } from '@/components/Chat/ResultChart'
import { DataTable } from '@/components/Chat/DataTable'
import { ScheduleModal } from '@/components/Schedule/ScheduleModal'

function ReportRunModal({ data, chart, onClose }: { data: QueryData; chart: ChartConfig; onClose: () => void }) {
  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.7)',
    }}>
      <div style={{
        background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-lg)',
        width: '100%', maxWidth: 720, padding: 28, maxHeight: '80vh', overflowY: 'auto',
      }} className="animate-fade-in">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 28, fontWeight: 400, letterSpacing: '-0.01em' }}>Результат</h2>
          <button onClick={onClose} className="btn ghost sm icon" style={{ fontSize: 18 }}>×</button>
        </div>
        {chart.type !== 'table' && (
          <div className="chart-card" style={{ marginBottom: 16 }}>
            <ResultChart data={data} chart={chart} />
          </div>
        )}
        <DataTable data={data} defaultOpen />
      </div>
    </div>
  )
}

const CHART_COLORS_IDX = ['var(--accent)', 'var(--blue)', 'var(--violet)', 'var(--cyan)', 'var(--amber)', 'var(--green)']

export default function ReportsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [scope, setScope] = useState<'all' | 'mine' | 'public'>('all')
  const [search, setSearch] = useState('')
  const [runResult, setRunResult] = useState<{ data: QueryData; chart: ChartConfig } | null>(null)
  const [scheduleReport, setScheduleReport] = useState<Report | null>(null)

  const { data: reports = [], isLoading } = useQuery({
    queryKey: ['reports', scope],
    queryFn: () => listReports(scope),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteReport,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
  })

  const runMutation = useMutation({
    mutationFn: runReport,
    onSuccess: (result) => {
      if (result.data && result.chart) {
        setRunResult({ data: result.data as QueryData, chart: result.chart as ChartConfig })
      }
      qc.invalidateQueries({ queryKey: ['reports'] })
    },
  })

  const filtered = reports.filter((r) =>
    r.name.toLowerCase().includes(search.toLowerCase()) ||
    (r.original_question || '').toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1440, margin: '0 auto' }}>
      {/* Page head */}
      <div className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>/ reports</div>
          <h1 className="page-title">Сохранённые <em>отчёты</em></h1>
        </div>
        <div className="page-meta">
          {reports.length} отчётов<br />
          последний запуск сегодня
        </div>
      </div>

      {/* Filter row */}
      <div className="filter-row">
        <div className="search">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
            <circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/>
          </svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Найти отчёт или задать новый вопрос…"
          />
          <span className="kbd">/</span>
        </div>

        <div style={{ display: 'flex', gap: 2, background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)', borderRadius: 'var(--radius-md)', padding: 3 }}>
          {(['all', 'mine', 'public'] as const).map((s) => (
            <button
              key={s}
              onClick={() => setScope(s)}
              className={`btn sm${scope === s ? ' primary' : ' ghost'}`}
            >
              {s === 'all' ? 'Все' : s === 'mine' ? 'Мои' : 'Публичные'}
            </button>
          ))}
        </div>

        <button
          onClick={() => navigate('/chat')}
          className="btn primary"
        >
          <Plus size={13} /> Новый вопрос
        </button>
      </div>

      {/* Reports grid */}
      {isLoading && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Загрузка...
        </div>
      )}

      {!isLoading && filtered.length === 0 && (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <p style={{ color: 'var(--text-muted)', fontSize: 15 }}>Нет отчётов</p>
          <button onClick={() => navigate('/chat')} className="btn primary" style={{ marginTop: 16 }}>
            Задать вопрос
          </button>
        </div>
      )}

      <div className="report-grid">
        {filtered.map((report, i) => (
          <div key={report.id} className={`report-card idx-${i % 6}`}>
            <div className="rc-head">
              <div style={{ flex: 1 }}>
                <div className="rc-title">{report.name}</div>
                {report.description && (
                  <div className="rc-desc">{report.description}</div>
                )}
              </div>
              <span className="chip" style={{ fontSize: 10.5, padding: '3px 8px', flexShrink: 0 }}>
                {report.chart_type || 'table'}
              </span>
            </div>

            {/* Mini chart preview */}
            <div className="rc-preview" style={{ alignItems: 'flex-end' }}>
              {[0.4, 0.7, 0.55, 0.9, 0.65, 0.45, 0.8].map((h, j) => (
                <div
                  key={j}
                  className="b"
                  style={{
                    height: `${h * 100}%`,
                    background: CHART_COLORS_IDX[i % CHART_COLORS_IDX.length],
                    opacity: 0.7 + j * 0.04,
                  }}
                />
              ))}
            </div>

            <div className="rc-meta">
              <span>👤 {report.owner.username}</span>
              <span>{formatDate(report.created_at)}</span>
              {report.is_public ? (
                <span style={{ color: 'var(--green)' }}>публичный</span>
              ) : (
                <span>приватный</span>
              )}
              {report.has_schedule && <span style={{ color: 'var(--blue)' }}>🔁 расписание</span>}
            </div>

            <div className="rc-footer">
              <div className="status">
                <span className="ddd" />
                Готов
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  onClick={() => runMutation.mutate(report.id)}
                  disabled={runMutation.isPending}
                  className="btn ghost sm icon"
                  title="Запустить"
                >
                  <Play size={13} />
                </button>
                <button
                  onClick={() => navigate(`/reports/${report.id}`)}
                  className="btn ghost sm icon"
                  title="Открыть"
                >
                  <Eye size={13} />
                </button>
                <button
                  onClick={() => setScheduleReport(report)}
                  className="btn ghost sm icon"
                  title="Расписание"
                >
                  <Calendar size={13} />
                </button>
                <button
                  onClick={() => exportReportPdf(report.id)}
                  className="btn ghost sm icon"
                  title="Экспорт PDF"
                >
                  <Download size={13} />
                </button>
                <button
                  onClick={() => { if (confirm(`Удалить «${report.name}»?`)) deleteMutation.mutate(report.id) }}
                  className="btn ghost sm icon"
                  title="Удалить"
                  style={{ color: 'var(--text-muted)' }}
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {runResult && (
        <ReportRunModal
          data={runResult.data}
          chart={runResult.chart}
          onClose={() => setRunResult(null)}
        />
      )}

      {scheduleReport && (
        <ScheduleModal
          report={scheduleReport}
          onClose={() => setScheduleReport(null)}
        />
      )}
    </div>
  )
}
