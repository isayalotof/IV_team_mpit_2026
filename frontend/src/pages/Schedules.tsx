import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Pause, Play, Trash2 } from 'lucide-react'
import { listSchedules, updateSchedule, deleteSchedule } from '@/api/schedules'
import { formatDate } from '@/lib/utils'

export default function SchedulesPage() {
  const qc = useQueryClient()
  const { data: schedules = [], isLoading } = useQuery({
    queryKey: ['schedules'],
    queryFn: listSchedules,
  })

  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      updateSchedule(id, { enabled } as never),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedules'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: deleteSchedule,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['schedules'] }),
  })

  const deliveryLabels: Record<string, string> = {
    none: 'только история',
    telegram: 'Telegram',
    email: 'Email',
  }

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1440, margin: '0 auto' }}>
      {/* Page head */}
      <div className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>/ schedules</div>
          <h1 className="page-title">Авто-<em>пересчёт</em> и доставка</h1>
        </div>
        <div className="page-meta">
          APScheduler · {schedules.filter(s => s.enabled).length} активных<br />
          автодоставка в Telegram
        </div>
      </div>

      {isLoading && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
          Загрузка...
        </div>
      )}

      {!isLoading && schedules.length === 0 && (
        <div style={{ textAlign: 'center', padding: '80px 0' }}>
          <p style={{ color: 'var(--text-muted)', fontSize: 15 }}>Нет активных расписаний</p>
          <p style={{ color: 'var(--text-faint)', fontSize: 13, marginTop: 6, fontFamily: 'var(--font-mono)' }}>
            Создайте расписание из карточки отчёта
          </p>
        </div>
      )}

      <div>
        {schedules.map((s, i) => (
          <div
            key={s.id}
            className="sched-item"
            style={{ opacity: s.enabled ? 1 : 0.55 }}
          >
            {/* Glyph */}
            <div className="sched-glyph">
              {String(i + 1).padStart(2, '0')}
            </div>

            {/* Info */}
            <div className="sched-info">
              <div className="title">{s.report_id}</div>
              <div className="row">
                <span>
                  <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
                  </svg>
                  {s.cron}
                </span>
                <span style={{ color: 'var(--text-muted)' }}>{s.timezone}</span>
                <span style={{ color: s.delivery_type === 'telegram' ? 'var(--blue)' : 'var(--text-muted)' }}>
                  {deliveryLabels[s.delivery_type] || s.delivery_type}
                </span>
                {s.delivery_targets.length > 0 && (
                  <span>{s.delivery_targets.join(', ')}</span>
                )}
              </div>
            </div>

            {/* Next run */}
            <div className="sched-next">
              {s.last_run_at && (
                <>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11, fontFamily: 'var(--font-mono)' }}>последний</div>
                  <div>{formatDate(s.last_run_at)}</div>
                </>
              )}
              <div style={{ marginTop: 4, fontSize: 11, fontFamily: 'var(--font-mono)' }}>
                {s.last_run_status === 'failure' ? (
                  <span style={{ color: 'var(--red)' }}>● ошибка</span>
                ) : s.last_run_at ? (
                  <span style={{ color: 'var(--green)' }}>● успешно</span>
                ) : (
                  <span style={{ color: 'var(--text-muted)' }}>ожидание</span>
                )}
              </div>
            </div>

            {/* Status chip */}
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
              <span
                className={s.enabled ? 'role-chip role-analyst' : 'role-chip'}
                style={!s.enabled ? { background: 'var(--bg-elevated)', color: 'var(--text-muted)' } : {}}
              >
                {s.enabled ? 'активно' : 'пауза'}
              </span>
              <div style={{ display: 'flex', gap: 4 }}>
                <button
                  onClick={() => toggleMutation.mutate({ id: s.id, enabled: !s.enabled })}
                  className="btn ghost sm icon"
                  title={s.enabled ? 'Поставить на паузу' : 'Возобновить'}
                >
                  {s.enabled ? <Pause size={13} /> : <Play size={13} />}
                </button>
                <button
                  onClick={() => { if (confirm('Удалить расписание?')) deleteMutation.mutate(s.id) }}
                  className="btn ghost sm icon"
                >
                  <Trash2 size={13} />
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
