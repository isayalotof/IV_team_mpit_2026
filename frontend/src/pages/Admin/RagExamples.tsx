import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Trash2, Plus, Database, Zap, User } from 'lucide-react'
import client from '@/api/client'

interface RagExample {
  id: number
  question: string
  sql: string
  source: 'seed' | 'manual' | 'auto'
  confidence: number
  created_at: string
}

interface RagData {
  examples: RagExample[]
  stats: Record<string, number>
}

const SOURCE_LABELS: Record<string, { label: string; color: string; Icon: React.ElementType }> = {
  seed:   { label: 'seed',   color: 'var(--blue)',   Icon: Database },
  manual: { label: 'manual', color: 'var(--accent)',  Icon: User },
  auto:   { label: 'auto',   color: 'var(--green)',   Icon: Zap },
}

export default function RagExamplesPage() {
  const qc = useQueryClient()
  const [newQ, setNewQ] = useState('')
  const [newSQL, setNewSQL] = useState('')
  const [addError, setAddError] = useState('')

  const { data, isLoading } = useQuery<RagData>({
    queryKey: ['rag'],
    queryFn: async () => (await client.get('/admin/rag')).data,
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => client.delete(`/admin/rag/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rag'] }),
  })

  const addMut = useMutation({
    mutationFn: (body: { question: string; sql: string }) => client.post('/admin/rag', body),
    onSuccess: () => {
      setNewQ('')
      setNewSQL('')
      setAddError('')
      qc.invalidateQueries({ queryKey: ['rag'] })
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Ошибка'
      setAddError(msg)
    },
  })

  const total = data ? Object.values(data.stats).reduce((a, b) => a + b, 0) : 0

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1200, margin: '0 auto' }}>
      <div className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>/ admin · rag examples</div>
          <h1 className="page-title">RAG Few-shot Store</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 6 }}>
            Векторная база примеров (вопрос → SQL). Используется как динамические few-shots при генерации.
            Пополняется автоматически при уверенных LLM-запросах.
          </p>
        </div>
      </div>

      {/* Stats */}
      <div className="admin-stat-grid" style={{ marginBottom: 28 }}>
        <div className="stat-card">
          <div className="stat-value">{total}</div>
          <div className="stat-label">всего примеров</div>
        </div>
        {Object.entries(SOURCE_LABELS).map(([src, meta]) => (
          <div key={src} className="stat-card">
            <div className="stat-value" style={{ color: meta.color }}>{data?.stats[src] ?? 0}</div>
            <div className="stat-label">{meta.label}</div>
          </div>
        ))}
      </div>

      {/* Add form */}
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-lg)', padding: 20, marginBottom: 28,
      }}>
        <div className="eyebrow" style={{ marginBottom: 14 }}>Добавить пример вручную</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          <input
            value={newQ}
            onChange={e => setNewQ(e.target.value)}
            placeholder="Вопрос на русском…"
            style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
              borderRadius: 6, padding: '9px 12px', color: 'var(--text-primary)',
              fontSize: 13, fontFamily: 'inherit', width: '100%',
            }}
          />
          <textarea
            value={newSQL}
            onChange={e => setNewSQL(e.target.value)}
            placeholder="SELECT … FROM …"
            rows={3}
            style={{
              background: 'var(--bg-elevated)', border: '1px solid var(--border-default)',
              borderRadius: 6, padding: '9px 12px', color: 'var(--text-primary)',
              fontSize: 12, fontFamily: 'var(--font-mono)', width: '100%', resize: 'vertical',
            }}
          />
          {addError && <p style={{ color: 'var(--red)', fontSize: 12 }}>{addError}</p>}
          <button
            onClick={() => addMut.mutate({ question: newQ.trim(), sql: newSQL.trim() })}
            disabled={!newQ.trim() || !newSQL.trim() || addMut.isPending}
            className="btn primary sm"
            style={{ alignSelf: 'flex-start' }}
          >
            <Plus size={13} /> Добавить
          </button>
        </div>
      </div>

      {/* Table */}
      {isLoading ? (
        <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Загрузка…</div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          {(data?.examples ?? []).map(ex => {
            const srcMeta = SOURCE_LABELS[ex.source] ?? SOURCE_LABELS.manual
            const SrcIcon = srcMeta.Icon
            return (
              <div
                key={ex.id}
                style={{
                  background: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
                  borderRadius: 8, padding: '12px 16px',
                  display: 'grid', gridTemplateColumns: '1fr 1.6fr auto', gap: 16, alignItems: 'start',
                }}
              >
                <div>
                  <div style={{ fontSize: 13, color: 'var(--text-primary)', marginBottom: 4 }}>{ex.question}</div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                    <span style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      fontSize: 10, fontFamily: 'var(--font-mono)', color: srcMeta.color,
                      background: 'var(--bg-elevated)', padding: '2px 7px', borderRadius: 4,
                    }}>
                      <SrcIcon size={9} /> {srcMeta.label}
                    </span>
                    {ex.confidence < 1 && (
                      <span style={{ fontSize: 10, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                        conf {Math.round(ex.confidence * 100)}%
                      </span>
                    )}
                  </div>
                </div>
                <code style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)',
                  background: 'var(--bg-elevated)', padding: '6px 10px', borderRadius: 5,
                  display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                }}>
                  {ex.sql}
                </code>
                <button
                  onClick={() => deleteMut.mutate(ex.id)}
                  className="btn ghost sm icon"
                  style={{ color: 'var(--red)', opacity: 0.7 }}
                  title="Удалить"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            )
          })}
          {(data?.examples ?? []).length === 0 && (
            <div style={{ color: 'var(--text-muted)', fontSize: 13 }}>Примеров пока нет.</div>
          )}
        </div>
      )}
    </div>
  )
}
