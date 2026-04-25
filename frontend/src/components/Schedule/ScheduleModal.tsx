import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { createSchedule } from '@/api/schedules'
import { Report } from '@/types'

interface Props {
  report: Report
  onClose: () => void
}

const CRON_PRESETS = [
  { label: 'Ежедневно в 09:00', cron: '0 9 * * *' },
  { label: 'Ежедневно в 18:00', cron: '0 18 * * *' },
  { label: 'Еженедельно (ПН в 09:00)', cron: '0 9 * * 1' },
  { label: 'Ежемесячно (1-го в 09:00)', cron: '0 9 1 * *' },
]

export function ScheduleModal({ report, onClose }: Props) {
  const qc = useQueryClient()
  const [cron, setCron] = useState('0 9 * * *')
  const [deliveryType, setDeliveryType] = useState<'none' | 'telegram' | 'email'>('none')
  const [targets, setTargets] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleSave = async () => {
    setLoading(true)
    setError('')
    try {
      await createSchedule({
        report_id: report.id,
        cron,
        delivery_type: deliveryType,
        delivery_targets: targets ? targets.split(',').map((s) => s.trim()).filter(Boolean) : [],
      })
      qc.invalidateQueries({ queryKey: ['schedules'] })
      qc.invalidateQueries({ queryKey: ['reports'] })
      onClose()
    } catch (e: unknown) {
      const msg = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setError(msg ? `Ошибка: ${msg}` : 'Не удалось создать расписание')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-bg-elevated border border-border-default rounded-xl shadow-lg w-full max-w-md p-6 animate-fade-in">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-base font-semibold text-text-primary">Настроить расписание</h2>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary">
            <X size={16} />
          </button>
        </div>

        <p className="text-xs text-text-muted mb-4">{report.name}</p>

        <div className="space-y-4">
          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Частота</label>
            <div className="grid grid-cols-2 gap-2 mb-2">
              {CRON_PRESETS.map((p) => (
                <button
                  key={p.cron}
                  onClick={() => setCron(p.cron)}
                  className={`text-xs px-3 py-2 rounded-md border transition-colors ${
                    cron === p.cron
                      ? 'border-accent-primary text-accent-primary bg-accent-bg'
                      : 'border-border-default text-text-secondary hover:bg-bg-hover'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            <div>
              <label className="text-xs text-text-muted mb-1 block">Или cron выражение</label>
              <input
                value={cron}
                onChange={(e) => setCron(e.target.value)}
                className="w-full bg-bg-base border border-border-default rounded-md px-3 py-2 text-sm font-mono text-text-primary focus:border-accent-primary focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-text-secondary mb-1.5">Доставка</label>
            <div className="flex gap-2">
              {(['none', 'telegram', 'email'] as const).map((t) => (
                <button
                  key={t}
                  onClick={() => setDeliveryType(t)}
                  className={`flex-1 py-1.5 text-xs rounded-md border transition-colors ${
                    deliveryType === t
                      ? 'border-accent-primary text-accent-primary bg-accent-bg'
                      : 'border-border-default text-text-secondary hover:bg-bg-hover'
                  }`}
                >
                  {t === 'none' ? 'Только сохранить' : t === 'telegram' ? 'Telegram' : 'Email'}
                </button>
              ))}
            </div>
          </div>

          {deliveryType !== 'none' && (
            <div>
              <label className="block text-xs font-medium text-text-secondary mb-1">
                {deliveryType === 'telegram' ? 'Chat ID (через запятую)' : 'Email адреса (через запятую)'}
              </label>
              <input
                value={targets}
                onChange={(e) => setTargets(e.target.value)}
                placeholder={deliveryType === 'telegram' ? '-1001234567890' : 'user@example.com'}
                className="w-full bg-bg-base border border-border-default rounded-md px-3 py-2 text-sm text-text-primary placeholder:text-text-muted focus:border-accent-primary focus:outline-none"
              />
            </div>
          )}

          {error && <p className="text-xs text-error">{error}</p>}
        </div>

        <div className="flex gap-2 mt-5">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 text-sm rounded-md border border-border-default text-text-secondary hover:bg-bg-hover transition-colors"
          >
            Отмена
          </button>
          <button
            onClick={handleSave}
            disabled={loading}
            className="flex-1 px-4 py-2 text-sm rounded-md bg-accent-primary text-accent-text font-medium hover:bg-accent-hover disabled:opacity-50 transition-colors"
          >
            {loading ? 'Сохранение...' : 'Создать расписание'}
          </button>
        </div>
      </div>
    </div>
  )
}
