import { Confidence } from '@/types'

const LEVEL_CONFIG = {
  high: { confClass: 'conf-high', dots: 4, label: 'HIGH' },
  medium: { confClass: 'conf-med', dots: 3, label: 'MED' },
  low: { confClass: 'conf-low', dots: 2, label: 'LOW' },
}

interface Props {
  confidence: Confidence
}

export function ConfidenceIndicator({ confidence }: Props) {
  const cfg = LEVEL_CONFIG[confidence.level]
  const pct = Math.round(confidence.score * 100)

  return (
    <span
      className={`confidence ${cfg.confClass}`}
      title={confidence.explanation}
    >
      <span className="conf-dots">
        {[1, 2, 3, 4].map((i) => (
          <span key={i} className={i <= cfg.dots ? 'on' : ''} />
        ))}
      </span>
      {cfg.label} {pct}%
    </span>
  )
}
