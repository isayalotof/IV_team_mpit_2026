import { useState } from 'react'
import { Copy, Check, ChevronDown, ChevronRight } from 'lucide-react'

interface Props {
  sql: string
  source?: string
}

const SQL_KEYWORDS = /\b(SELECT|FROM|WHERE|JOIN|LEFT|RIGHT|INNER|OUTER|ON|GROUP BY|ORDER BY|HAVING|LIMIT|OFFSET|WITH|AS|AND|OR|NOT|IN|BETWEEN|LIKE|IS|NULL|DISTINCT|COUNT|SUM|AVG|MIN|MAX|CASE|WHEN|THEN|ELSE|END|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER|TABLE|INDEX|VIEW|UNION|ALL|EXISTS)\b/gi
const SQL_STRINGS = /'[^']*'/g
const SQL_NUMBERS = /\b\d+(\.\d+)?\b/g
const SQL_COMMENTS = /--[^\n]*/g
const SQL_FUNCTIONS = /\b(COALESCE|NULLIF|CAST|CONVERT|DATE|YEAR|MONTH|DAY|NOW|CURRENT_DATE|CURRENT_TIMESTAMP|EXTRACT|DATE_TRUNC|TO_CHAR|UPPER|LOWER|TRIM|REPLACE|SUBSTRING|LENGTH|CONCAT|ROUND|FLOOR|CEIL|ABS|GREATEST|LEAST|ROW_NUMBER|RANK|DENSE_RANK|LAG|LEAD|OVER|PARTITION)\b/gi

function highlightSQL(sql: string): string {
  // We'll use a simple approach: escape HTML, then apply color spans
  const escaped = sql
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // Apply highlighting in order (comments first to avoid double-wrapping)
  return escaped
    .replace(SQL_COMMENTS, (m) => `<span class="cmt">${m}</span>`)
    .replace(SQL_STRINGS, (m) => `<span class="str">${m}</span>`)
    .replace(SQL_FUNCTIONS, (m) => `<span class="fn">${m}</span>`)
    .replace(SQL_KEYWORDS, (m) => `<span class="kw">${m.toUpperCase()}</span>`)
    .replace(SQL_NUMBERS, (m) => `<span class="num">${m}</span>`)
}

export function SqlBlock({ sql, source }: Props) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    await navigator.clipboard.writeText(sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const sourceLabel = source === 'template' ? 'template' : source === 'llm_corrected' ? 'llm+corrected' : source || 'llm'
  const lineCount = sql.split('\n').length

  return (
    <div className="sql-block">
      <div className="sql-header">
        <span className="tag">
          generated sql · <b>{sourceLabel}</b> · {lineCount} lines
        </span>
        <div className="sql-actions">
          <button
            className="btn sm ghost"
            onClick={() => setOpen(!open)}
          >
            {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
            {open ? 'Свернуть' : 'Показать'}
          </button>
          <button
            className="btn sm ghost"
            onClick={handleCopy}
            title="Копировать SQL"
          >
            {copied ? <Check size={12} style={{ color: 'var(--green)' }} /> : <Copy size={12} />}
            {copied ? 'Скопировано' : 'Копировать'}
          </button>
        </div>
      </div>

      {open && (
        <div
          className="sql-code"
          dangerouslySetInnerHTML={{ __html: highlightSQL(sql) }}
        />
      )}
    </div>
  )
}
