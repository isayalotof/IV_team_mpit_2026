import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { LayoutDashboard, Trash2, Plus, Download } from 'lucide-react'
import { listDashboards, createDashboard, deleteDashboard, exportDashboardPdf } from '@/api/dashboards'
import { Dashboard } from '@/types'
import { formatDate } from '@/lib/utils'

function CreateDashboardModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (name: string, description: string, isPublic: boolean) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPublic, setIsPublic] = useState(false)

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.7)',
    }}>
      <div style={{
        background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-xl)', boxShadow: 'var(--shadow-lg)',
        width: '100%', maxWidth: 480, padding: 28,
      }} className="animate-fade-in">
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <h2 style={{ fontFamily: 'var(--font-serif)', fontSize: 24, fontWeight: 400 }}>Новый дашборд</h2>
          <button onClick={onClose} className="btn ghost sm icon" style={{ fontSize: 18 }}>×</button>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
              Название *
            </label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Операционный дашборд"
              style={{
                width: '100%', padding: '10px 12px', background: 'var(--bg-input)',
                border: '1px solid var(--border-default)', borderRadius: 8,
                color: 'var(--text-primary)', fontSize: 14, boxSizing: 'border-box',
              }}
              autoFocus
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6 }}>
              Описание
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Ключевые метрики по выручке и водителям"
              rows={3}
              style={{
                width: '100%', padding: '10px 12px', background: 'var(--bg-input)',
                border: '1px solid var(--border-default)', borderRadius: 8,
                color: 'var(--text-primary)', fontSize: 14, resize: 'vertical', boxSizing: 'border-box',
              }}
            />
          </div>
          <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontSize: 14 }}>
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            <span>Публичный дашборд</span>
          </label>
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10, marginTop: 24 }}>
          <button className="btn ghost" onClick={onClose}>Отмена</button>
          <button
            className="btn primary"
            disabled={!name.trim()}
            onClick={() => { if (name.trim()) onCreate(name.trim(), description.trim(), isPublic) }}
          >
            Создать
          </button>
        </div>
      </div>
    </div>
  )
}

export default function DashboardsPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const [showCreate, setShowCreate] = useState(false)

  const { data: dashboards = [], isLoading } = useQuery({
    queryKey: ['dashboards'],
    queryFn: listDashboards,
  })

  const createMutation = useMutation({
    mutationFn: createDashboard,
    onSuccess: (dashboard) => {
      qc.invalidateQueries({ queryKey: ['dashboards'] })
      setShowCreate(false)
      navigate(`/dashboards/${dashboard.id}`)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: deleteDashboard,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dashboards'] }),
  })

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1440, margin: '0 auto' }}>
      <div className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>/ dashboards</div>
          <h1 className="page-title">Дашборды</h1>
        </div>
        <button className="btn primary" onClick={() => setShowCreate(true)}>
          <Plus size={15} /> Новый дашборд
        </button>
      </div>

      {isLoading ? (
        <div style={{ color: 'var(--text-muted)', marginTop: 48, textAlign: 'center' }}>Загрузка…</div>
      ) : dashboards.length === 0 ? (
        <div style={{ marginTop: 80, textAlign: 'center' }}>
          <LayoutDashboard size={48} style={{ color: 'var(--text-muted)', marginBottom: 16 }} />
          <p style={{ color: 'var(--text-secondary)', fontSize: 16, marginBottom: 8 }}>
            Нет дашбордов
          </p>
          <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
            Создайте дашборд и добавьте в него сохранённые отчёты
          </p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
          gap: 20,
          marginTop: 28,
        }}>
          {dashboards.map((d) => (
            <DashboardCard
              key={d.id}
              dashboard={d}
              onOpen={() => navigate(`/dashboards/${d.id}`)}
              onDelete={() => {
                if (confirm(`Удалить дашборд «${d.name}»?`)) {
                  deleteMutation.mutate(d.id)
                }
              }}
              onExport={() => exportDashboardPdf(d.id)}
            />
          ))}
        </div>
      )}

      {showCreate && (
        <CreateDashboardModal
          onClose={() => setShowCreate(false)}
          onCreate={(name, description, isPublic) => {
            createMutation.mutate({ name, description, is_public: isPublic })
          }}
        />
      )}
    </div>
  )
}

function DashboardCard({ dashboard, onOpen, onDelete, onExport }: {
  dashboard: Dashboard
  onOpen: () => void
  onDelete: () => void
  onExport: () => void
}) {
  return (
    <div
      className="card"
      style={{ cursor: 'pointer', transition: 'border-color 0.15s' }}
      onClick={onOpen}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <LayoutDashboard size={16} style={{ color: 'var(--accent)', flexShrink: 0, marginTop: 2 }} />
          <span style={{ fontSize: 15, fontWeight: 600, color: 'var(--text-primary)', lineHeight: 1.3 }}>
            {dashboard.name}
          </span>
        </div>
        <div style={{ display: 'flex', gap: 4 }} onClick={(e) => e.stopPropagation()}>
          <button
            className="btn ghost sm icon"
            onClick={onExport}
            title="Экспорт PDF"
          >
            <Download size={13} />
          </button>
          <button
            className="btn ghost sm icon"
            style={{ color: 'var(--text-muted)' }}
            onClick={onDelete}
            title="Удалить"
          >
            <Trash2 size={13} />
          </button>
        </div>
      </div>

      {dashboard.description && (
        <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginBottom: 10, lineHeight: 1.4 }}>
          {dashboard.description}
        </p>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 8 }}>
        {dashboard.is_public && (
          <span style={{
            fontSize: 11, padding: '2px 8px', borderRadius: 999,
            background: 'rgba(232,255,92,0.12)', color: 'var(--accent)', fontWeight: 600,
          }}>
            PUBLIC
          </span>
        )}
        <span style={{ fontSize: 12, color: 'var(--text-muted)', marginLeft: 'auto' }}>
          {formatDate(dashboard.updated_at)}
        </span>
      </div>
    </div>
  )
}
