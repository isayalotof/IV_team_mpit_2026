import { useState, useEffect } from 'react'
import { Save, RotateCcw, AlertCircle, HelpCircle, Database, ChevronRight, AlertTriangle, Bookmark, Clipboard, TrendingUp, TrendingDown } from 'lucide-react'
import { QueryResponse, QueryData } from '@/types'
import { ConfidenceIndicator } from './ConfidenceIndicator'
import { InterpretationChips } from './InterpretationChips'
import { SqlBlock } from './SqlBlock'
import { ResultChart } from './ResultChart'
import { DataTable } from './DataTable'
import { SaveReportModal } from './SaveReportModal'
import { useAuthStore } from '@/store/auth'
import { addRagExample } from '@/api/admin'

interface BotMessageProps {
  response: QueryResponse
  onReformulate?: (text: string) => void
  originalQuestion?: string
}

function PeriodDeltaBlock({ data }: { data: QueryData }) {
  if (data.rows.length !== 2) return null
  const cols = data.columns.map(c => c.name)
  const valIdx = cols.findIndex(c => c === 'value' || c.includes('cnt') || c.includes('count') || c.includes('sum'))
  if (valIdx < 0) return null
  const a = Number(data.rows[0][valIdx]) || 0
  const b = Number(data.rows[1][valIdx]) || 0
  const labelA = String(data.rows[0][0] ?? '')
  const labelB = String(data.rows[1][0] ?? '')
  const delta = a - b
  const pct = b !== 0 ? ((delta / Math.abs(b)) * 100).toFixed(1) : null
  const up = delta >= 0

  const fmt = (v: number) => {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`
    return String(Math.round(v))
  }

  return (
    <div className="period-delta">
      <span className="pd-item"><span className="pd-label">{labelA}</span><b>{fmt(a)}</b></span>
      <span className="pd-sep">vs</span>
      <span className="pd-item"><span className="pd-label">{labelB}</span><b>{fmt(b)}</b></span>
      <span className={`pd-delta ${up ? 'pd-up' : 'pd-down'}`}>
        {up ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
        {up ? '+' : ''}{fmt(delta)}{pct !== null && ` (${up ? '+' : ''}${pct}%)`}
      </span>
    </div>
  )
}

export function BotMessage({ response, onReformulate, originalQuestion }: BotMessageProps) {
  const [showSaveModal, setShowSaveModal] = useState(false)
  const [savedId, setSavedId] = useState<string | null>(null)
  const [savedTemplate, setSavedTemplate] = useState(false)
  const { isRole } = useAuthStore()

  const handleSaveAsTemplate = async () => {
    if (!originalQuestion || !response.sql) return
    try {
      await addRagExample(originalQuestion, response.sql)
      setSavedTemplate(true)
    } catch {
      // non-critical
    }
  }

  if (response.status === 'ambiguous') {
    return (
      <div className="msg animate-slide-up">
        <div className="msg-avatar" style={{ background: 'var(--amber-soft)', color: 'var(--amber)' }}>
          <HelpCircle size={13} />
        </div>
        <div className="msg-body">
          <div className="msg-name">AskData · уточнение</div>
          <div className="ambig">
            <div className="ambig-head">
              <span className="tag">Уточните, пожалуйста</span>
            </div>
            <div style={{ color: 'var(--text-secondary)', fontSize: 13.5, marginBottom: 12 }}>
              Запрос можно интерпретировать несколькими способами. Выберите один:
            </div>
            {response.suggestions && response.suggestions.length > 0 && (
              <div className="ambig-options">
                {response.suggestions.map((s, i) => (
                  <button
                    key={i}
                    className="ambig-opt"
                    onClick={() => onReformulate?.(s.text)}
                  >
                    <span className="opt-num">{String(i + 1).padStart(2, '0')}</span>
                    <span className="opt-txt">{s.text}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  if (response.status === 'error') {
    return (
      <div className="msg animate-slide-up">
        <div className="msg-avatar" style={{ background: 'var(--red-soft)', color: 'var(--red)' }}>
          <AlertCircle size={13} />
        </div>
        <div className="msg-body">
          <div className="msg-name">AskData · ошибка</div>
          <div style={{
            padding: '12px 16px', background: 'var(--red-soft)', border: '1px solid var(--red)',
            borderRadius: 'var(--radius-md)', fontSize: 13, color: 'var(--red)',
            fontFamily: 'var(--font-mono)',
          }}>
            {typeof response.detail === 'string'
              ? response.detail
              : 'Не удалось выполнить запрос. Попробуйте переформулировать.'}
          </div>
          {onReformulate && originalQuestion && (
            <button
              onClick={() => onReformulate(originalQuestion)}
              className="btn ghost sm"
              style={{ marginTop: 8 }}
            >
              <RotateCcw size={12} />
              Переформулировать
            </button>
          )}
        </div>
      </div>
    )
  }

  const hasChart = response.chart && response.chart.type !== 'table' && response.data?.rows.length
  const tableDefaultOpen = !hasChart || (response.data?.row_count ?? 0) <= 20

  return (
    <>
      <div className="msg animate-slide-up">
        <div className="msg-avatar bot">A</div>

        <div className="msg-body">
          <div className="msg-name">AskData</div>

          <div className="response">
            {/* Interpretation + Confidence */}
            {response.interpretation && (
              <div className="resp-row" style={{ flexWrap: 'wrap', gap: 10 }}>
                <InterpretationChips interpretation={response.interpretation} />
                {response.confidence && <ConfidenceIndicator confidence={response.confidence} />}
              </div>
            )}

            {/* Explanation */}
            {response.explanation && (
              <div className="explainer">
                <span>
                  {response.explanation.split(/\*\*(.+?)\*\*/g).map((part, i) =>
                    i % 2 === 1 ? <b key={i}>{part}</b> : part
                  )}
                </span>
              </div>
            )}

            {/* SQL */}
            {response.sql && <SqlBlock sql={response.sql} source={response.sql_source} />}

            {/* Period comparison delta */}
            {response.template_id === 'period_comparison' && response.data && (
              <PeriodDeltaBlock data={response.data} />
            )}

            {/* Chart */}
            {hasChart && response.data && response.chart && (
              <div className="chart-card">
                <div className="chart-head">
                  <div>
                    <div className="chart-title">{response.chart.title || 'Результат'}</div>
                    <div className="chart-sub">
                      {response.data.row_count} строк · {response.data.columns.length} колонок
                      {response.execution_ms !== undefined && ` · ${response.execution_ms} мс`}
                    </div>
                  </div>
                </div>
                <ResultChart data={response.data} chart={response.chart} />
              </div>
            )}

            {/* Table */}
            {response.data && (
              <DataTable data={response.data} defaultOpen={tableDefaultOpen} />
            )}

            {/* Low-confidence suggestions */}
            {response.suggestions && response.suggestions.length > 0 && (
              <div className="ambig" style={{ borderColor: 'var(--amber)' }}>
                <div className="ambig-head">
                  <AlertTriangle size={13} style={{ color: 'var(--amber)', flexShrink: 0 }} />
                  <span className="tag">Результат может быть неточным — уточните запрос:</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {response.suggestions.map((s, i) => (
                    <button
                      key={i}
                      onClick={() => onReformulate?.(s.text)}
                      className="ambig-opt"
                      style={{ display: 'flex', alignItems: 'center', gap: 8 }}
                    >
                      <ChevronRight size={11} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                      <span style={{ fontSize: 13 }}>{s.text}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Human-in-the-loop for low confidence */}
            {response.confidence && response.confidence.score < 0.5 && (
              <div className="human-loop">
                <span className="human-loop-label">
                  Уверенность низкая ({Math.round(response.confidence.score * 100)}%) — хотите уточнить?
                </span>
                <div className="human-loop-actions">
                  {onReformulate && originalQuestion && (
                    <button className="btn sm" onClick={() => onReformulate(originalQuestion)}>
                      <RotateCcw size={11} /> Переформулировать
                    </button>
                  )}
                  <button
                    className="btn sm ghost"
                    onClick={() => originalQuestion && navigator.clipboard.writeText(originalQuestion)}
                    title="Скопировать вопрос в буфер"
                  >
                    <Clipboard size={11} /> Скопировать вопрос
                  </button>
                </div>
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              {!savedId ? (
                <button
                  onClick={() => setShowSaveModal(true)}
                  className="btn sm"
                >
                  <Save size={12} />
                  Сохранить отчёт
                </button>
              ) : (
                <span style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '5px 10px', background: 'var(--green-soft)', color: 'var(--green)',
                  borderRadius: 'var(--radius-md)', fontSize: 12, fontFamily: 'var(--font-mono)',
                }}>
                  ✓ Сохранено
                </span>
              )}

              {onReformulate && originalQuestion && (
                <button
                  onClick={() => onReformulate(originalQuestion)}
                  className="btn sm ghost"
                >
                  <RotateCcw size={12} />
                  Переформулировать
                </button>
              )}

              {isRole('analyst') && response.sql && originalQuestion && (
                !savedTemplate ? (
                  <button onClick={handleSaveAsTemplate} className="btn sm ghost" title="Сохранить вопрос+SQL в базу шаблонов команды">
                    <Bookmark size={12} /> Шаблон команды
                  </button>
                ) : (
                  <span style={{ fontSize: 11, color: 'var(--green)', fontFamily: 'var(--font-mono)' }}>
                    ✓ В шаблонах
                  </span>
                )
              )}

              {response.execution_ms !== undefined && (
                <span style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
                  {response.execution_ms} мс
                </span>
              )}
            </div>
          </div>
        </div>
      </div>

      {showSaveModal && (
        <SaveReportModal
          response={response}
          onClose={() => setShowSaveModal(false)}
          onSaved={(id) => setSavedId(id)}
        />
      )}
    </>
  )
}

interface UserMessageProps {
  text: string
}

export function UserMessage({ text }: UserMessageProps) {
  return (
    <div className="msg animate-fade-in" style={{ justifyContent: 'flex-end' }}>
      <div className="msg-body" style={{ maxWidth: 560 }}>
        <div className="msg-text user-text">{text}</div>
      </div>
      <div className="msg-avatar user">U</div>
    </div>
  )
}

// Stages advance after these delays (ms). The last stage runs until the response arrives.
const PIPELINE_STAGES = [
  { label: 'препроцессинг', delay: 0 },
  { label: 'генерирую SQL', delay: 300 },
  { label: 'выполняю запрос', delay: 1800 },
  { label: 'оцениваю результат', delay: 3800 },
]

export function TypingIndicator() {
  const [stage, setStage] = useState(0)

  useEffect(() => {
    const timers = PIPELINE_STAGES.slice(1).map((s, i) =>
      setTimeout(() => setStage(i + 1), s.delay)
    )
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div className="msg animate-fade-in">
      <div className="msg-avatar bot">A</div>
      <div className="msg-body">
        <div className="msg-name">AskData</div>
        <div className="pipeline">
          {PIPELINE_STAGES.map((s, i) => (
            <span key={i} style={{ display: 'inline-flex', alignItems: 'center', gap: 0 }}>
              {i > 0 && <span className="pipe-sep">→</span>}
              <span className={`pipe-step${i === stage ? ' active' : i < stage ? ' done' : ''}`}>
                <span className={`pin${i === stage ? ' pulse' : ''}`} />
                {s.label}
              </span>
            </span>
          ))}
        </div>
      </div>
    </div>
  )
}

interface SchemaTable {
  name: string
  columns: { name: string; type: string }[]
  row_count?: number
}

interface SchemaData {
  tables?: SchemaTable[]
  whitelist_tables?: string[]
  metrics?: Record<string, { description: string; format?: string }>
}

export function SchemaMessage({ schemaData }: { schemaData: SchemaData }) {
  const [expanded, setExpanded] = useState<string | null>(null)

  const tables: SchemaTable[] = schemaData?.tables || []
  const metrics = schemaData?.metrics || {}

  return (
    <div className="msg animate-slide-up">
      <div className="msg-avatar" style={{ background: 'var(--blue-soft)', color: 'var(--blue)' }}>
        <Database size={13} />
      </div>
      <div className="msg-body">
        <div className="msg-name">Schema · доступные данные</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 600 }}>

          {/* Metrics */}
          {Object.keys(metrics).length > 0 && (
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Метрики</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 }}>
                {Object.entries(metrics).map(([key, m]) => (
                  <div key={key} style={{
                    padding: '8px 12px', background: 'var(--bg-elevated)',
                    border: '1px solid var(--border-default)', borderRadius: 6,
                  }}>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>{key}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 2 }}>{m.description}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Tables */}
          {tables.length > 0 && (
            <div>
              <div className="eyebrow" style={{ marginBottom: 8 }}>Таблицы</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                {tables.map((t) => (
                  <div key={t.name} style={{ border: '1px solid var(--border-default)', borderRadius: 6, overflow: 'hidden' }}>
                    <button
                      onClick={() => setExpanded(expanded === t.name ? null : t.name)}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        padding: '8px 12px', background: 'var(--bg-elevated)', cursor: 'pointer',
                        border: 'none', fontFamily: 'inherit', color: 'var(--text-primary)',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <ChevronRight
                          size={13}
                          style={{ color: 'var(--text-muted)', transform: expanded === t.name ? 'rotate(90deg)' : '', transition: 'transform 0.15s' }}
                        />
                        <span style={{ fontSize: 13, fontFamily: 'var(--font-mono)' }}>{t.name}</span>
                        {t.row_count !== undefined && (
                          <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>{t.row_count.toLocaleString('ru-RU')} строк</span>
                        )}
                      </div>
                      <span style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>{t.columns?.length ?? 0} col</span>
                    </button>
                    {expanded === t.name && t.columns?.length > 0 && (
                      <div style={{ borderTop: '1px solid var(--border-subtle)' }}>
                        <table className="data-table">
                          <thead>
                            <tr>
                              <th>Колонка</th>
                              <th>Тип</th>
                            </tr>
                          </thead>
                          <tbody>
                            {t.columns.map((col) => (
                              <tr key={col.name}>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>{col.name}</td>
                                <td style={{ color: 'var(--text-muted)' }}>{col.type}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {tables.length === 0 && Object.keys(metrics).length === 0 && (
            <p style={{ fontSize: 13, color: 'var(--text-muted)' }}>Схема не загружена.</p>
          )}
        </div>
      </div>
    </div>
  )
}
