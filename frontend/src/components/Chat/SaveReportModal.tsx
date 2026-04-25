import { useState } from 'react'
import { X, Calendar, CheckCircle } from 'lucide-react'
import { createReport } from '@/api/reports'
import { createSchedule } from '@/api/schedules'
import { QueryResponse } from '@/types'

interface Props {
  response: QueryResponse
  onClose: () => void
  onSaved: (reportId: string) => void
}

const FREQ_OPTIONS = [
  { label: 'Каждый день в 9:00', cron: '0 9 * * *' },
  { label: 'Каждый понедельник в 9:00', cron: '0 9 * * 1' },
  { label: 'Первого числа месяца', cron: '0 9 1 * *' },
]

export function SaveReportModal({ response, onClose, onSaved }: Props) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [isPublic, setIsPublic] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [savedReportId, setSavedReportId] = useState<string | null>(null)

  // Schedule section
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [freqIdx, setFreqIdx] = useState(0)
  const [delivery, setDelivery] = useState<'telegram' | 'email' | 'none'>('none')
  const [target, setTarget] = useState('')
  const [schedSaving, setSchedSaving] = useState(false)
  const [schedDone, setSchedDone] = useState(false)
  const [schedError, setSchedError] = useState('')

  const handleSave = async () => {
    if (!name.trim()) {
      setError('Введите название отчёта')
      return
    }
    if (!response.sql) {
      setError('SQL не найден')
      return
    }
    setLoading(true)
    try {
      const report = await createReport({
        name: name.trim(),
        description: description.trim() || undefined,
        sql: response.sql,
        is_public: isPublic,
        interpretation: response.interpretation,
        chart_config: response.chart,
        columns_meta: response.data?.columns,
      })
      setSavedReportId(report.id)
      onSaved(report.id)
    } catch {
      setError('Не удалось сохранить отчёт')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateSchedule = async () => {
    if (!savedReportId) return
    const targets = delivery !== 'none' && target.trim() ? [target.trim()] : []
    setSchedSaving(true)
    setSchedError('')
    try {
      await createSchedule({
        report_id: savedReportId,
        cron: FREQ_OPTIONS[freqIdx].cron,
        timezone: 'Europe/Moscow',
        delivery_type: delivery,
        delivery_targets: targets,
        enabled: true,
      })
      setSchedDone(true)
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } }
      setSchedError(err.response?.data?.detail || 'Не удалось создать расписание')
    } finally {
      setSchedSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-bg-elevated border border-border-default rounded-xl shadow-lg w-full max-w-md p-6 animate-fade-in">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-text-primary">Сохранить отчёт</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary transition-colors">
            <X size={16} />
          </button>
        </div>

        {!savedReportId ? (
          <>
            <div className="space-y-3">
              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Название *</label>
                <input
                  autoFocus
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="Например: Отмены по городам за неделю"
                  className="w-full bg-bg-base border border-border-default rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-primary focus:outline-none transition-colors"
                />
              </div>

              <div>
                <label className="block text-xs font-medium text-text-secondary mb-1">Описание</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Опциональное описание..."
                  rows={2}
                  className="w-full bg-bg-base border border-border-default rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-primary focus:outline-none transition-colors resize-none"
                />
              </div>

              <label className="flex items-center gap-2.5 cursor-pointer">
                <input
                  type="checkbox"
                  checked={isPublic}
                  onChange={(e) => setIsPublic(e.target.checked)}
                  className="w-4 h-4 rounded accent-accent-primary"
                />
                <span className="text-sm text-text-secondary">Публичный (виден всем)</span>
              </label>

              {error && <p className="text-xs text-red-400">{error}</p>}
            </div>

            <div className="flex gap-2 mt-5">
              <button
                onClick={onClose}
                className="flex-1 px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:text-text-primary hover:bg-bg-hover transition-colors"
              >
                Отмена
              </button>
              <button
                onClick={handleSave}
                disabled={loading}
                className="flex-1 px-4 py-2 text-sm rounded-md bg-accent-primary text-accent-text font-medium hover:bg-accent-hover disabled:opacity-50 transition-colors"
              >
                {loading ? 'Сохранение...' : 'Сохранить'}
              </button>
            </div>
          </>
        ) : (
          <>
            {/* Saved state — offer schedule */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: 'var(--green-soft)', borderRadius: 8, marginBottom: 16 }}>
              <CheckCircle size={15} style={{ color: 'var(--green)', flexShrink: 0 }} />
              <span style={{ fontSize: 13, color: 'var(--green)', fontFamily: 'var(--font-mono)' }}>Отчёт сохранён</span>
            </div>

            {!schedDone ? (
              <>
                <button
                  onClick={() => setScheduleOpen(o => !o)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8, width: '100%',
                    padding: '10px 14px', background: 'var(--bg-surface)',
                    border: '1px solid var(--border-default)', borderRadius: 8,
                    cursor: 'pointer', fontFamily: 'inherit', color: 'var(--text-primary)',
                    fontSize: 13, marginBottom: 12,
                  }}
                >
                  <Calendar size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                  Отправлять по расписанию
                  <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)' }}>
                    {scheduleOpen ? '▲' : '▼'}
                  </span>
                </button>

                {scheduleOpen && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 12 }}>
                    <div>
                      <label style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 4 }}>
                        Частота
                      </label>
                      <select
                        value={freqIdx}
                        onChange={e => setFreqIdx(Number(e.target.value))}
                        style={{
                          width: '100%', padding: '8px 12px', background: 'var(--bg-input)',
                          border: '1px solid var(--border-default)', borderRadius: 6,
                          color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit',
                        }}
                      >
                        {FREQ_OPTIONS.map((f, i) => (
                          <option key={i} value={i}>{f.label}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 4 }}>
                        Доставка
                      </label>
                      <select
                        value={delivery}
                        onChange={e => setDelivery(e.target.value as 'telegram' | 'email' | 'none')}
                        style={{
                          width: '100%', padding: '8px 12px', background: 'var(--bg-input)',
                          border: '1px solid var(--border-default)', borderRadius: 6,
                          color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit',
                        }}
                      >
                        <option value="none">Только хранить</option>
                        <option value="email">Email</option>
                        <option value="telegram">Telegram</option>
                      </select>
                    </div>

                    {delivery !== 'none' && (
                      <div>
                        <label style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', textTransform: 'uppercase', letterSpacing: '0.08em', display: 'block', marginBottom: 4 }}>
                          {delivery === 'email' ? 'Email адрес' : 'Telegram chat ID'}
                        </label>
                        <input
                          value={target}
                          onChange={e => setTarget(e.target.value)}
                          placeholder={delivery === 'email' ? 'you@company.ru' : '-100123456789'}
                          style={{
                            width: '100%', padding: '8px 12px', background: 'var(--bg-input)',
                            border: '1px solid var(--border-default)', borderRadius: 6,
                            color: 'var(--text-primary)', fontSize: 13, fontFamily: 'inherit',
                          }}
                        />
                      </div>
                    )}

                    {schedError && (
                      <p style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--font-mono)' }}>{schedError}</p>
                    )}

                    <button
                      onClick={handleCreateSchedule}
                      disabled={schedSaving}
                      className="btn primary"
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      {schedSaving ? 'Создаю...' : 'Создать расписание'}
                    </button>
                  </div>
                )}
              </>
            ) : (
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 14px', background: 'var(--accent-soft)', borderRadius: 8, marginBottom: 12 }}>
                <Calendar size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                <span style={{ fontSize: 13, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>
                  Расписание создано — {FREQ_OPTIONS[freqIdx].label.toLowerCase()}
                </span>
              </div>
            )}

            <button
              onClick={onClose}
              className="btn"
              style={{ width: '100%', justifyContent: 'center' }}
            >
              Закрыть
            </button>
          </>
        )}
      </div>
    </div>
  )
}
