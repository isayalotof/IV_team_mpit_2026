import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ArrowLeft, Play, Plus, Trash2, Download, LayoutDashboard, RefreshCw, GripVertical } from 'lucide-react'
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core'
import {
  SortableContext,
  sortableKeyboardCoordinates,
  rectSortingStrategy,
  useSortable,
  arrayMove,
} from '@dnd-kit/sortable'
import { CSS } from '@dnd-kit/utilities'
import { getDashboard, runDashboard, addWidget, removeWidget, reorderWidgets, exportDashboardPdf } from '@/api/dashboards'
import { listReports } from '@/api/reports'
import { ResultChart } from '@/components/Chat/ResultChart'
import { DataTable } from '@/components/Chat/DataTable'
import { DashboardWidget, DashboardWidgetResult, Report, QueryData, ChartConfig } from '@/types'

const REFRESH_OPTIONS = [
  { label: 'Откл.', value: 0 },
  { label: '30 сек', value: 30 },
  { label: '1 мин', value: 60 },
  { label: '5 мин', value: 300 },
]

function AddWidgetModal({ dashboardId, onClose }: { dashboardId: string; onClose: () => void }) {
  const qc = useQueryClient()
  const [search, setSearch] = useState('')
  const [selected, setSelected] = useState<string | null>(null)
  const [titleOverride, setTitleOverride] = useState('')

  const { data: reports = [] } = useQuery({
    queryKey: ['reports', 'all'],
    queryFn: () => listReports('all'),
  })

  const addMutation = useMutation({
    mutationFn: () => addWidget(dashboardId, {
      report_id: selected!,
      title_override: titleOverride.trim() || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dashboard', dashboardId] })
      onClose()
    },
  })

  const filtered = reports.filter((r: Report) =>
    r.name.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.75)',
    }}>
      <div style={{
        background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-lg)',
        width: '100%', maxWidth: 540, padding: 28, maxHeight: '80vh', display: 'flex', flexDirection: 'column',
      }} className="animate-fade-in">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 22, fontWeight: 400 }}>Добавить отчёт</h2>
          <button onClick={onClose} className="btn ghost sm icon" style={{ fontSize: 18 }}>×</button>
        </div>

        <input
          placeholder="Поиск отчётов…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            width: '100%', padding: '9px 12px', background: 'var(--bg-input)',
            border: '1px solid var(--border-default)', borderRadius: 8,
            color: 'var(--text-primary)', fontSize: 13, marginBottom: 12, boxSizing: 'border-box',
          }}
          autoFocus
        />

        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
          {filtered.map((r: Report) => (
            <div
              key={r.id}
              onClick={() => setSelected(r.id)}
              style={{
                padding: '10px 12px', borderRadius: 8, cursor: 'pointer',
                border: `1px solid ${selected === r.id ? 'var(--accent)' : 'var(--border-default)'}`,
                background: selected === r.id ? 'rgba(232,255,92,0.07)' : 'var(--bg-card)',
                transition: 'all 0.12s',
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{r.name}</div>
              {r.original_question && (
                <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 2 }}>{r.original_question}</div>
              )}
            </div>
          ))}
          {filtered.length === 0 && (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '24px 0', fontSize: 13 }}>
              Отчёты не найдены
            </div>
          )}
        </div>

        {selected && (
          <div style={{ marginTop: 14 }}>
            <input
              placeholder="Заголовок (необязательно)"
              value={titleOverride}
              onChange={(e) => setTitleOverride(e.target.value)}
              style={{
                width: '100%', padding: '9px 12px', background: 'var(--bg-input)',
                border: '1px solid var(--border-default)', borderRadius: 8,
                color: 'var(--text-primary)', fontSize: 13, boxSizing: 'border-box',
              }}
            />
          </div>
        )}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 16 }}>
          <button className="btn ghost" onClick={onClose}>Отмена</button>
          <button
            className="btn primary"
            disabled={!selected || addMutation.isPending}
            onClick={() => addMutation.mutate()}
          >
            Добавить
          </button>
        </div>
      </div>
    </div>
  )
}

function SortableWidgetCard({
  result,
  widget,
  onRemove,
  isDragging: externalDragging,
}: {
  result?: DashboardWidgetResult
  widget: DashboardWidget
  onRemove?: () => void
  isDragging?: boolean
}) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: widget.id })

  const style: React.CSSProperties = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.4 : 1,
    zIndex: isDragging ? 10 : undefined,
  }

  return (
    <div ref={setNodeRef} style={style}>
      <WidgetCard result={result} widget={widget} onRemove={onRemove} dragHandleProps={{ ...attributes, ...listeners }} />
    </div>
  )
}

function WidgetCard({
  result,
  widget,
  onRemove,
  dragHandleProps,
}: {
  result?: DashboardWidgetResult
  widget: DashboardWidget
  onRemove?: () => void
  dragHandleProps?: Record<string, unknown>
}) {
  const [showTable, setShowTable] = useState(false)
  const title = result?.title ?? widget.title_override ?? widget.report?.name ?? widget.report_id

  const hasChart = result?.chart && result.chart.type !== 'table'
  const hasData = result?.data && result.data.rows.length > 0
  const isPlaceholder = !result

  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, minWidth: 0 }}>
          <span
            {...dragHandleProps}
            style={{
              cursor: 'grab', color: 'var(--text-muted)', flexShrink: 0,
              display: 'flex', alignItems: 'center', touchAction: 'none',
            }}
            title="Перетащить"
          >
            <GripVertical size={14} />
          </span>
          <span style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {title}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
          {hasData && (
            <button
              className="btn ghost sm"
              style={{ fontSize: 11 }}
              onClick={() => setShowTable((v) => !v)}
            >
              {showTable ? 'График' : 'Таблица'}
            </button>
          )}
          {onRemove && (
            <button className="btn ghost sm icon" onClick={onRemove} title="Удалить виджет">
              <Trash2 size={12} />
            </button>
          )}
        </div>
      </div>

      {isPlaceholder ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '16px 0', textAlign: 'center' }}>
          Нажмите «Запустить» для загрузки данных
        </div>
      ) : result.error ? (
        <div style={{ color: '#ff6b6b', fontSize: 13, padding: '8px 0' }}>
          Ошибка: {result.error}
        </div>
      ) : !hasData ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 13, padding: '8px 0' }}>Нет данных</div>
      ) : showTable ? (
        <DataTable data={result.data as QueryData} defaultOpen />
      ) : hasChart ? (
        <div className="chart-card">
          <ResultChart data={result.data as QueryData} chart={result.chart as ChartConfig} />
        </div>
      ) : (
        <DataTable data={result.data as QueryData} defaultOpen />
      )}
    </div>
  )
}

export default function DashboardDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const qc = useQueryClient()

  const [results, setResults] = useState<DashboardWidgetResult[]>([])
  const [showAddWidget, setShowAddWidget] = useState(false)
  const [isRunning, setIsRunning] = useState(false)
  const [isExporting, setIsExporting] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [refreshInterval, setRefreshInterval] = useState(0)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)
  const [widgetOrder, setWidgetOrder] = useState<string[]>([])
  const refreshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: dashboard, isLoading } = useQuery({
    queryKey: ['dashboard', id],
    queryFn: () => getDashboard(id!),
    enabled: !!id,
  })

  useEffect(() => {
    if (dashboard?.widgets) {
      setWidgetOrder(dashboard.widgets.map((w) => w.id))
    }
  }, [dashboard])

  const reorderMutation = useMutation({
    mutationFn: (order: string[]) => reorderWidgets(id!, order),
  })

  const removeWidgetMutation = useMutation({
    mutationFn: (widgetId: string) => removeWidget(id!, widgetId),
    onSuccess: (_data, widgetId) => {
      qc.invalidateQueries({ queryKey: ['dashboard', id] })
      setResults((prev) => prev.filter((r) => r.widget_id !== widgetId))
    },
  })

  const handleRun = useCallback(async () => {
    if (!id) return
    setIsRunning(true)
    setRunError(null)
    try {
      const res = await runDashboard(id)
      setResults(res)
      setLastRefreshed(new Date())
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } }; message?: string })
        ?.response?.data?.detail ?? (e as { message?: string })?.message ?? 'Не удалось запустить дашборд'
      setRunError(msg)
    } finally {
      setIsRunning(false)
    }
  }, [id])

  const handleExportPdf = async () => {
    if (!id || !dashboard) return
    setIsExporting(true)
    try {
      await exportDashboardPdf(id, dashboard.name)
    } finally {
      setIsExporting(false)
    }
  }

  // Auto-refresh timer
  useEffect(() => {
    if (refreshTimerRef.current) {
      clearInterval(refreshTimerRef.current)
      refreshTimerRef.current = null
    }
    if (refreshInterval > 0) {
      refreshTimerRef.current = setInterval(() => {
        handleRun()
      }, refreshInterval * 1000)
    }
    return () => {
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current)
    }
  }, [refreshInterval, handleRun])

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  )

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event
    if (!over || active.id === over.id) return

    setWidgetOrder((prev) => {
      const oldIndex = prev.indexOf(active.id as string)
      const newIndex = prev.indexOf(over.id as string)
      const newOrder = arrayMove(prev, oldIndex, newIndex)
      reorderMutation.mutate(newOrder)
      return newOrder
    })
  }

  if (isLoading) {
    return <div style={{ padding: '40px', color: 'var(--text-muted)', textAlign: 'center' }}>Загрузка…</div>
  }

  if (!dashboard) {
    return <div style={{ padding: '40px', color: 'var(--text-muted)', textAlign: 'center' }}>Дашборд не найден</div>
  }

  const widgets = dashboard.widgets ?? []
  const sortedWidgets = widgetOrder
    .map((wid) => widgets.find((w) => w.id === wid))
    .filter((w): w is DashboardWidget => !!w)
  const resultsMap = Object.fromEntries(results.map((r) => [r.widget_id, r]))

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1440, margin: '0 auto' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <button className="btn ghost sm icon" onClick={() => navigate('/dashboards')} title="Назад">
          <ArrowLeft size={16} />
        </button>
        <div style={{ flex: 1 }}>
          <div className="eyebrow" style={{ marginBottom: 4 }}>/ dashboards</div>
          <h1 style={{ fontFamily: 'var(--font-serif)', fontSize: 32, fontWeight: 400, margin: 0, letterSpacing: '-0.01em' }}>
            {dashboard.name}
          </h1>
          {dashboard.description && (
            <p style={{ color: 'var(--text-secondary)', fontSize: 14, margin: '4px 0 0' }}>
              {dashboard.description}
            </p>
          )}
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          {/* Auto-refresh selector */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <RefreshCw size={13} style={{ color: refreshInterval > 0 ? 'var(--accent)' : 'var(--text-muted)' }} />
            <select
              value={refreshInterval}
              onChange={(e) => setRefreshInterval(Number(e.target.value))}
              style={{
                background: 'var(--bg-input)', border: '1px solid var(--border-default)',
                borderRadius: 8, color: 'var(--text-secondary)', fontSize: 12,
                padding: '5px 8px', cursor: 'pointer',
              }}
            >
              {REFRESH_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {lastRefreshed && (
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              обновлено {lastRefreshed.toLocaleTimeString('ru')}
            </span>
          )}

          <button
            className="btn ghost"
            onClick={handleExportPdf}
            disabled={isExporting || widgets.length === 0}
            title="Экспорт PDF"
          >
            <Download size={14} /> {isExporting ? 'Генерирую…' : 'PDF'}
          </button>
          <button className="btn ghost" onClick={() => setShowAddWidget(true)}>
            <Plus size={14} /> Добавить
          </button>
          <button
            className="btn primary"
            onClick={handleRun}
            disabled={isRunning || widgets.length === 0}
          >
            <Play size={14} /> {isRunning ? 'Выполняю…' : 'Запустить'}
          </button>
        </div>
      </div>

      {/* Run error banner */}
      {runError && (
        <div style={{
          marginBottom: 16, padding: '10px 16px', borderRadius: 8,
          background: 'rgba(255,107,107,0.1)', border: '1px solid rgba(255,107,107,0.35)',
          color: '#ff6b6b', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <span>Ошибка выполнения: {runError}</span>
          <button onClick={() => setRunError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ff6b6b', fontSize: 16, lineHeight: 1, padding: '0 4px' }}>×</button>
        </div>
      )}

      {/* Content */}
      {sortedWidgets.length === 0 ? (
        <div style={{ marginTop: 80, textAlign: 'center' }}>
          <LayoutDashboard size={48} style={{ color: 'var(--text-muted)', marginBottom: 16 }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: 16, marginBottom: 8 }}>Дашборд пустой</p>
          <p style={{ color: 'var(--text-muted)', fontSize: 14, marginBottom: 20 }}>
            Добавьте сохранённые отчёты, чтобы увидеть их здесь
          </p>
          <button className="btn primary" onClick={() => setShowAddWidget(true)}>
            <Plus size={14} /> Добавить отчёт
          </button>
        </div>
      ) : (
        <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
          <SortableContext items={widgetOrder} strategy={rectSortingStrategy}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(480px, 1fr))',
              gap: 20,
            }}>
              {sortedWidgets.map((w) => (
                <SortableWidgetCard
                  key={w.id}
                  widget={w}
                  result={resultsMap[w.id]}
                  onRemove={() => {
                    if (confirm('Удалить виджет?')) removeWidgetMutation.mutate(w.id)
                  }}
                />
              ))}
            </div>
          </SortableContext>
        </DndContext>
      )}

      {showAddWidget && (
        <AddWidgetModal dashboardId={id!} onClose={() => setShowAddWidget(false)} />
      )}
    </div>
  )
}
