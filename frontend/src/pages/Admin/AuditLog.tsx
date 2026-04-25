import { useQuery } from '@tanstack/react-query'
import client from '@/api/client'
import { AuditLog } from '@/types'
import { formatDate } from '@/lib/utils'

export default function AuditLogPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['audit'],
    queryFn: async () => {
      const { data } = await client.get('/admin/audit?limit=100')
      return data.logs as AuditLog[]
    },
  })

  const confColor = (c?: number) => {
    if (!c) return 'var(--text-muted)'
    if (c >= 0.9) return 'var(--green)'
    if (c >= 0.5) return 'var(--amber)'
    return 'var(--red)'
  }

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1440, margin: '0 auto' }}>
      {/* Page head */}
      <div className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>/ admin · audit log</div>
          <h1 className="page-title">Журнал <em>аудита</em></h1>
        </div>
        <div className="page-meta">
          прозрачность · безопасность<br />
          {data ? `${data.length} записей` : 'загрузка...'}
        </div>
      </div>

      {isLoading && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Загрузка...
        </div>
      )}

      {data && (
        <div className="rp-card" style={{ padding: 0, overflow: 'hidden' }}>
          {/* Header row */}
          <div className="audit-row head">
            <span>TIME</span>
            <span>USER</span>
            <span>QUESTION</span>
            <span>MS</span>
            <span>CONF</span>
            <span>SRC</span>
          </div>

          {data.map((log) => (
            <div
              key={log.id}
              className="audit-row"
              style={{ cursor: 'default' }}
            >
              <span className="time">{formatDate(log.created_at)}</span>
              <span className="user">{log.user_id}</span>
              <span className="q" title={log.question} style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {log.question}
              </span>
              <span className="ms">—</span>
              <span
                className="ms"
                style={{ color: confColor(log.confidence), textAlign: 'right' }}
              >
                {log.confidence != null ? `${Math.round(log.confidence * 100)}%` : '—'}
              </span>
              <span className="src">
                {log.violations?.length ? (
                  <span style={{ color: 'var(--red)', fontSize: 10 }}>⚠ {log.violations[0]}</span>
                ) : log.error ? (
                  <span style={{ color: 'var(--red)' }}>err</span>
                ) : (
                  <span style={{ color: 'var(--green)' }}>✓</span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
