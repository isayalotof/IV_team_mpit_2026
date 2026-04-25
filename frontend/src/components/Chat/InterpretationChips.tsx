import { Interpretation } from '@/types'

interface Props {
  interpretation: Interpretation
}

export function InterpretationChips({ interpretation }: Props) {
  const slots: { label: string; value: string }[] = []

  if (interpretation.metric) {
    slots.push({ label: 'метрика', value: interpretation.metric })
  }
  if (interpretation.grouping) {
    slots.push({ label: 'разрез', value: interpretation.grouping })
  }
  if (interpretation.period?.label) {
    slots.push({ label: 'период', value: interpretation.period.label })
  }
  if (interpretation.filters?.length > 0) {
    slots.push({ label: 'фильтр', value: interpretation.filters.join(', ') })
  }

  if (slots.length === 0) return null

  return (
    <div className="interp-block">
      <span className="interp-eyebrow">Я понял тебя так</span>
      <div className="interp-slots">
        {slots.map((s, i) => (
          <span key={s.label} className="interp-slot">
            {i > 0 && <span className="interp-sep">·</span>}
            <span className="interp-label">{s.label}:</span>
            <b className="interp-value">{s.value}</b>
          </span>
        ))}
      </div>
    </div>
  )
}
