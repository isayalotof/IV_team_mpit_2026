import { useState, useRef, useEffect, useCallback } from 'react'
import { Send, Database, HelpCircle, Plus, Trash2, Mic, MicOff, Loader2, ChevronRight, X } from 'lucide-react'
import { useVoiceRecorder } from '@/hooks/useVoiceRecorder'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { runQuery, getSchema, getTemplates } from '@/api/query'
import { getSessions, getSessionMessages, deleteSession } from '@/api/sessions'
import { QueryResponse } from '@/types'
import { BotMessage, UserMessage, TypingIndicator, SchemaMessage } from '@/components/Chat/ChatMessage'

const EXAMPLE_QUESTIONS = [
  'Покажи отмены по городам за прошлую неделю',
  'Динамика выручки за последние 30 дней',
  'Топ 5 городов по числу поездок',
  'Среднее время онлайн водителей по городам за последний месяц',
  'Acceptance rate водителей за последние 2 недели',
  'Сколько новых пассажиров зарегистрировалось по неделям за последние 3 месяца',
]

const SLASH_COMMANDS = [
  { cmd: '/data', icon: Database, label: 'Показать доступные данные и таблицы' },
  { cmd: '/help', icon: HelpCircle, label: 'Показать список команд' },
]

interface Message {
  id: string
  type: 'user' | 'bot' | 'schema' | 'help'
  text?: string
  response?: QueryResponse
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  schemaData?: any
}

const SESSION_KEY = 'askdata_session_id'

function newSessionId() {
  return crypto.randomUUID()
}

function formatTime(iso: string) {
  const d = new Date(iso)
  const now = new Date()
  const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
  if (diffDays === 0) return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  if (diffDays === 1) return 'вчера'
  if (diffDays < 7) return d.toLocaleDateString('ru-RU', { weekday: 'short' })
  return d.toLocaleDateString('ru-RU', { day: 'numeric', month: 'short' })
}

export default function ChatPage() {
  const qc = useQueryClient()

  const [sessionId, setSessionId] = useState<string>(() => {
    return localStorage.getItem(SESSION_KEY) || newSessionId()
  })
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [showCommands, setShowCommands] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [lastResponse, setLastResponse] = useState<QueryResponse | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const [showTemplatesModal, setShowTemplatesModal] = useState(false)
  const [queryMode, setQueryMode] = useState<'easy' | 'expert'>(() => {
    return (localStorage.getItem('askdata_mode') as 'easy' | 'expert') || 'easy'
  })

  const toggleMode = () => {
    setQueryMode((m) => {
      const next = m === 'easy' ? 'expert' : 'easy'
      localStorage.setItem('askdata_mode', next)
      return next
    })
  }

  const { data: sessionsData } = useQuery({
    queryKey: ['sessions'],
    queryFn: getSessions,
    refetchInterval: false,
  })
  const sessions = sessionsData ?? []

  const { data: templatesData } = useQuery({
    queryKey: ['templates'],
    queryFn: getTemplates,
    staleTime: Infinity,
  })
  const allTemplates = templatesData ?? []

  useEffect(() => {
    localStorage.setItem(SESSION_KEY, sessionId)
  }, [sessionId])

  const loadHistory = useCallback(async (sid: string) => {
    setHistoryLoading(true)
    setMessages([])
    setLastResponse(null)
    try {
      const { messages: history } = await getSessionMessages(sid)
      if (history.length) {
        const restored: Message[] = history.map((m) => ({
          id: String(m.id),
          type: m.role === 'user' ? 'user' : 'bot',
          text: m.content,
          response: m.query_response as QueryResponse | undefined,
        }))
        setMessages(restored)
        // Set last bot response for right panel
        const lastBot = [...restored].reverse().find(m => m.type === 'bot' && m.response)
        if (lastBot?.response) setLastResponse(lastBot.response)
      }
    } catch {
      // new session — no history yet
    } finally {
      setHistoryLoading(false)
    }
  }, [])

  useEffect(() => {
    loadHistory(sessionId)
  }, [sessionId, loadHistory])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  const createNewSession = () => {
    const id = newSessionId()
    setSessionId(id)
    setMessages([])
    setLastResponse(null)
    qc.invalidateQueries({ queryKey: ['sessions'] })
    setTimeout(() => inputRef.current?.focus(), 100)
  }

  const switchSession = (id: string) => {
    if (id === sessionId) return
    setSessionId(id)
  }

  const removeSession = async (e: React.MouseEvent, id: string) => {
    e.stopPropagation()
    await deleteSession(id)
    qc.invalidateQueries({ queryKey: ['sessions'] })
    if (id === sessionId) {
      createNewSession()
    }
  }

  const handleSlashData = async () => {
    setLoading(true)
    try {
      const schema = await getSchema()
      setMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), type: 'schema', schemaData: schema },
      ])
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: Date.now().toString(), type: 'bot', response: { status: 'error', detail: 'Не удалось загрузить схему данных.' } },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleSlashHelp = () => {
    setMessages((prev) => [
      ...prev,
      { id: Date.now().toString(), type: 'help' },
    ])
  }

  const sendMessage = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed || loading) return

    setInput('')
    setShowCommands(false)

    if (trimmed === '/data') {
      setMessages((prev) => [...prev, { id: Date.now().toString(), type: 'user', text: trimmed }])
      await handleSlashData()
      return
    }
    if (trimmed === '/help') {
      setMessages((prev) => [...prev, { id: Date.now().toString(), type: 'user', text: trimmed }])
      handleSlashHelp()
      return
    }

    const userMsg: Message = { id: Date.now().toString(), type: 'user', text: trimmed }
    setMessages((prev) => [...prev, userMsg])
    setLoading(true)

    try {
      const response = await runQuery(trimmed, false, sessionId, queryMode)
      const botMsg: Message = {
        id: (Date.now() + 1).toString(),
        type: 'bot',
        response,
        text: trimmed,
      }
      setMessages((prev) => [...prev, botMsg])
      setLastResponse(response)
      qc.invalidateQueries({ queryKey: ['sessions'] })
    } catch (e: unknown) {
      const axiosError = e as { response?: { data?: QueryResponse } }
      const errorResponse: QueryResponse = axiosError.response?.data || {
        status: 'error',
        detail: 'Не удалось выполнить запрос. Проверьте подключение.',
      }
      setMessages((prev) => [
        ...prev,
        { id: (Date.now() + 1).toString(), type: 'bot', response: errorResponse, text: trimmed },
      ])
    } finally {
      setLoading(false)
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage(input)
    }
    if (e.key === 'Escape') setShowCommands(false)
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value
    setInput(val)
    setShowCommands(val === '/')
  }

  const { recording, processing: voiceProcessing, error: voiceError, toggle: toggleVoice } = useVoiceRecorder(
    (text) => setInput((prev) => (prev ? prev + ' ' + text : text))
  )

  const conf = lastResponse?.confidence
  const confClass = conf ? (conf.level === 'high' ? 'conf-high' : conf.level === 'medium' ? 'conf-med' : 'conf-low') : ''
  const confLabel = conf ? (conf.level === 'high' ? 'HIGH' : conf.level === 'medium' ? 'MED' : 'LOW') : null
  const confDots = conf ? (conf.level === 'high' ? 4 : conf.level === 'medium' ? 3 : 2) : 0

  return (
    <>
    <div className="chat-page">
    <div className="chat-grid" style={{ marginTop: 24 }}>

      {/* Left sidebar — sessions */}
      <aside className="chat-side">
        <div className="side-group">
          <button
            onClick={createNewSession}
            className="btn primary"
            style={{ width: '100%', justifyContent: 'center', marginBottom: 8 }}
          >
            <Plus size={13} /> Новый чат
          </button>

          <div className="side-label">Сессии</div>

          {historyLoading && (
            <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '4px 6px' }}>Загрузка...</div>
          )}

          {sessions.length === 0 && !historyLoading && (
            <div style={{ color: 'var(--text-muted)', fontSize: 12, padding: '4px 6px' }}>
              Нет сохранённых чатов
            </div>
          )}

          {sessions.map((s) => (
            <div
              key={s.id}
              className={`side-item${s.id === sessionId ? ' active' : ''}`}
              onClick={() => switchSession(s.id)}
            >
              <span className="dot" />
              <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {s.title}
              </span>
              <span className="tail">{formatTime(s.updated_at)}</span>
              <button
                onClick={(e) => removeSession(e, s.id)}
                style={{
                  padding: 2, borderRadius: 3, color: 'var(--text-muted)',
                  opacity: 0, transition: 'opacity 0.12s', marginLeft: 2,
                }}
                className="delete-btn"
                title="Удалить"
                onMouseEnter={e => (e.currentTarget.style.opacity = '1')}
                onMouseLeave={e => (e.currentTarget.style.opacity = '0')}
              >
                <Trash2 size={11} />
              </button>
            </div>
          ))}
        </div>

        <div className="side-group">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
            <div className="side-label" style={{ marginBottom: 0 }}>Шаблоны</div>
            <button
              onClick={() => setShowTemplatesModal(true)}
              style={{
                display: 'flex', alignItems: 'center', gap: 2,
                fontSize: 11, color: 'var(--accent)', background: 'none', border: 'none',
                cursor: 'pointer', fontFamily: 'var(--font-mono)', padding: '2px 4px',
                borderRadius: 3, transition: 'opacity 0.15s',
              }}
              title={`Показать все ${allTemplates.length || 18} шаблонов`}
            >
              все <ChevronRight size={10} />
            </button>
          </div>
          {EXAMPLE_QUESTIONS.slice(0, 5).map((q, i) => (
            <div
              key={q}
              className="side-item"
              onClick={() => sendMessage(q)}
            >
              <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--text-muted)', flexShrink: 0 }}>
                {String(i + 1).padStart(2, '0')}
              </span>
              <span style={{ flex: 1, fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {q}
              </span>
            </div>
          ))}
        </div>
      </aside>

      {/* Center — conversation + composer */}
      <section className="chat-main">
        {/* Conversation */}
        <div className="conv">
          {historyLoading && (
            <div style={{ textAlign: 'center', color: 'var(--text-muted)', fontSize: 12 }}>Загрузка истории...</div>
          )}

          {!historyLoading && messages.length === 0 && (
            <div className="animate-fade-in">
              <div className="msg">
                <div className="msg-avatar bot">A</div>
                <div className="msg-body">
                  <div className="msg-name">AskData</div>
                  <div className="msg-text" style={{ color: 'var(--text-secondary)', fontSize: 14 }}>
                    Готов отвечать на вопросы о данных Drivee. Спросите на русском — верну SQL, таблицу и график.
                    Введите <code style={{ background: 'var(--bg-elevated)', padding: '1px 6px', borderRadius: 3, color: 'var(--accent)', fontFamily: 'var(--font-mono)' }}>/data</code> чтобы увидеть доступные данные.
                  </div>
                </div>
              </div>
            </div>
          )}

          {messages.map((msg) => {
            if (msg.type === 'user') return <UserMessage key={msg.id} text={msg.text!} />
            if (msg.type === 'schema') return <SchemaMessage key={msg.id} schemaData={msg.schemaData} />
            if (msg.type === 'help') return <HelpMessage key={msg.id} />
            if (msg.type === 'bot' && msg.response) {
              return (
                <BotMessage
                  key={msg.id}
                  response={msg.response}
                  originalQuestion={msg.text}
                  onReformulate={(text) => sendMessage(text)}
                />
              )
            }
            return null
          })}

          {loading && <TypingIndicator />}
          <div ref={bottomRef} />
        </div>

        {/* Slash command popup */}
        {showCommands && (
          <div style={{
            margin: '0 48px 4px',
            border: '1px solid var(--border-default)',
            borderRadius: 8,
            background: 'var(--bg-elevated)',
            overflow: 'hidden',
            boxShadow: 'var(--shadow-md)',
          }}>
            {SLASH_COMMANDS.map(({ cmd, icon: CmdIcon, label }) => (
              <button
                key={cmd}
                onClick={() => sendMessage(cmd)}
                style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                  padding: '10px 16px', fontSize: 13, cursor: 'pointer',
                  background: 'none', border: 'none', fontFamily: 'inherit',
                  borderBottom: '1px solid var(--border-subtle)', color: 'var(--text-primary)',
                }}
              >
                <CmdIcon size={14} style={{ color: 'var(--accent)', flexShrink: 0 }} />
                <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--accent)', fontSize: 13 }}>{cmd}</span>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
              </button>
            ))}
          </div>
        )}

        {/* Composer */}
        <div className="composer">
          <div className="composer-chips">
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10.5, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.1em', marginRight: 6, alignSelf: 'center' }}>
              Попробуйте
            </span>
            {EXAMPLE_QUESTIONS.slice(0, 4).map((q, i) => (
              <button key={q} className="template-chip" onClick={() => sendMessage(q)}>
                <span className="tc-num">{String(i + 1).padStart(2, '0')}</span>
                {q}
              </button>
            ))}
          </div>
          <div className="composer-box">
            <textarea
              ref={inputRef}
              value={input}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Задайте вопрос на русском языке…"
              rows={1}
              style={{ minHeight: 44 }}
            />
            <button
              onClick={toggleMode}
              className="btn ghost sm mode-btn"
              title={queryMode === 'easy' ? 'Easy: система уточняет неполные запросы' : 'Expert: запрос уходит сразу без проверки'}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '0.04em',
                padding: '4px 8px',
                color: queryMode === 'expert' ? 'var(--accent)' : 'var(--text-muted)',
                borderColor: queryMode === 'expert' ? 'var(--accent)' : undefined,
                opacity: 0.85,
                flexShrink: 0,
              }}
            >
              {queryMode === 'easy' ? 'EASY' : 'EXPERT'}
            </button>
            <button
              onClick={toggleVoice}
              disabled={voiceProcessing}
              className="btn ghost sm icon"
              style={{
                color: recording ? 'var(--red)' : voiceProcessing ? 'var(--text-muted)' : 'var(--text-muted)',
              }}
              title={recording ? 'Остановить запись' : 'Голосовой ввод'}
            >
              {voiceProcessing ? (
                <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} />
              ) : recording ? (
                <MicOff size={15} />
              ) : (
                <Mic size={15} />
              )}
            </button>
            <button
              onClick={() => sendMessage(input)}
              disabled={!input.trim() || loading}
              className="btn primary sm"
            >
              {loading ? (
                <div style={{ width: 14, height: 14, border: '2px solid rgba(0,0,0,0.3)', borderTopColor: 'var(--accent-text)', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
              ) : (
                <Send size={14} />
              )}
              <span className="send-label">Спросить</span>
            </button>
          </div>
          {voiceError && (
            <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 4, fontFamily: 'var(--font-mono)' }}>{voiceError}</p>
          )}
          {recording && (
            <p style={{ fontSize: 11, color: 'var(--red)', marginTop: 4, fontFamily: 'var(--font-mono)', animation: 'pulseDot 1.5s infinite' }}>
              Запись... нажмите ещё раз для остановки
            </p>
          )}
        </div>
      </section>

      {/* Right panel — query metadata */}
      <aside className="chat-side chat-side-right" style={{ padding: 20, gap: 20 }}>
        {lastResponse && (
          <>
            <div className="side-group">
              <div className="side-label">Результат запроса</div>
              <div className="rp-card">
                {lastResponse.confidence && (
                  <div className="rp-kv">
                    <span className="k">Confidence</span>
                    <span className="v">
                      <span className={`confidence ${confClass}`} style={{ fontSize: 11 }}>
                        <span className="conf-dots">
                          {[1,2,3,4].map(i => (
                            <span key={i} className={i <= confDots ? 'on' : ''} />
                          ))}
                        </span>
                        {confLabel} {Math.round(lastResponse.confidence.score * 100)}%
                      </span>
                    </span>
                  </div>
                )}
                {lastResponse.sql_source && (
                  <div className="rp-kv">
                    <span className="k">Источник</span>
                    <span className="v">{lastResponse.sql_source}</span>
                  </div>
                )}
                {lastResponse.execution_ms !== undefined && (
                  <div className="rp-kv">
                    <span className="k">Время</span>
                    <span className="v ok">{lastResponse.execution_ms} мс</span>
                  </div>
                )}
                {lastResponse.data && (
                  <div className="rp-kv">
                    <span className="k">Строк</span>
                    <span className="v">{lastResponse.data.row_count}</span>
                  </div>
                )}
              </div>
            </div>

            <div className="side-group">
              <div className="side-label">Guardrails (7 слоёв)</div>
              <div className="rp-card">
                <div className="rp-kv"><span className="k">stmt</span><span className="v ok">SELECT only ✓</span></div>
                <div className="rp-kv"><span className="k">ops</span><span className="v ok">DDL/DML blocked ✓</span></div>
                <div className="rp-kv"><span className="k">funcs</span><span className="v ok">allowlist ✓</span></div>
                <div className="rp-kv"><span className="k">tables</span><span className="v ok">whitelist ✓</span></div>
                <div className="rp-kv"><span className="k">limit</span><span className="v">auto 1000</span></div>
                <div className="rp-kv"><span className="k">timeout</span><span className="v">30 с</span></div>
                <div className="rp-kv"><span className="k">db user</span><span className="v">askdata_reader</span></div>
              </div>
            </div>
          </>
        )}

        {!lastResponse && (
          <div className="side-group">
            <div className="side-label">Schema context</div>
            <div className="rp-card">
              <div className="rp-schema-tab">
                <span className="tbl">anonymized_incity_orders</span>
                <span className="col">order_id · tender_id <em>text</em></span>
                <span className="col">city_id <em>int</em></span>
                <span className="col">driver_id · user_id <em>text</em></span>
                <span className="col">status_order · status_tender <em>text</em></span>
                <span className="col">order_timestamp <em>timestamptz</em></span>
                <span className="col">price_order_local <em>numeric</em></span>
                <span className="col">distance_in_meters <em>numeric</em></span>
                <span className="tbl">driver_daily_stats</span>
                <span className="col">driver_id · city_id <em>text/int</em></span>
                <span className="col">tender_date_part <em>date</em></span>
                <span className="col">rides_count · online_time_sum_seconds <em>int</em></span>
                <span className="col">orders_cnt_accepted <em>int</em></span>
                <span className="tbl">passenger_daily_stats</span>
                <span className="col">user_id · city_id <em>text/int</em></span>
                <span className="col">order_date_part <em>date</em></span>
                <span className="col">rides_count · orders_count <em>int</em></span>
                <span className="tbl">cities</span>
                <span className="col">city_id <em>int pk</em></span>
                <span className="col">name <em>text</em></span>
              </div>
            </div>
          </div>
        )}

        <div className="side-group">
          <div className="side-label">Self-consistency</div>
          <div className="rp-card">
            <div className="rp-kv"><span className="k">runs</span><span className="v">2 × (T=0.1, T=0.7)</span></div>
            <div className="rp-kv">
              <span className="k">agreement</span>
              <span className={`v${lastResponse?.confidence?.level === 'high' ? ' ok' : lastResponse?.confidence?.level === 'medium' ? '' : ' warn'}`}>
                {lastResponse?.confidence?.explanation ?? '—'}
              </span>
            </div>
            <div className="rp-kv">
              <span className="k">path</span>
              <span className="v">{lastResponse?.sql_source ?? '—'}</span>
            </div>
          </div>
        </div>
      </aside>
    </div>
    </div>

    {/* Templates modal */}
    {showTemplatesModal && (
      <div
        style={{
          position: 'fixed', inset: 0, zIndex: 200,
          background: 'rgba(0,0,0,0.65)', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
        onClick={() => setShowTemplatesModal(false)}
      >
        <div
          style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border-default)',
            borderRadius: 12, width: 'min(780px, 92vw)', maxHeight: '80vh',
            display: 'flex', flexDirection: 'column', overflow: 'hidden',
            boxShadow: '0 24px 64px rgba(0,0,0,0.5)',
          }}
          onClick={(e) => e.stopPropagation()}
        >
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
            <div>
              <div style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-primary)' }}>Шаблоны запросов</div>
              <div style={{ fontSize: 11, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', marginTop: 2 }}>
                {allTemplates.length} шаблонов · нажмите чтобы задать вопрос
              </div>
            </div>
            <button onClick={() => setShowTemplatesModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)', padding: 4, borderRadius: 4 }}>
              <X size={16} />
            </button>
          </div>
          <div style={{ overflowY: 'auto', padding: '12px 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {allTemplates.map((t, i) => (
              <button
                key={t.id}
                onClick={() => { sendMessage(t.example); setShowTemplatesModal(false) }}
                style={{
                  background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
                  borderRadius: 8, padding: '10px 12px', cursor: 'pointer', textAlign: 'left',
                  transition: 'border-color 0.15s, background 0.15s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.background = 'var(--bg-hover)' }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; e.currentTarget.style.background = 'var(--bg-elevated)' }}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 10, color: 'var(--text-muted)', flexShrink: 0, marginTop: 2 }}>
                    {String(i + 1).padStart(2, '0')}
                  </span>
                  <div>
                    <div style={{ fontSize: 12, fontWeight: 500, color: 'var(--text-primary)', marginBottom: 2 }}>{t.title}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.4 }}>{t.description}</div>
                    <div style={{ fontSize: 10, color: 'var(--accent)', fontFamily: 'var(--font-mono)', marginTop: 4, opacity: 0.8 }}>
                      «{t.example}»
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    )}
    </>
  )
}

function HelpMessage() {
  return (
    <div className="msg animate-slide-up">
      <div className="msg-avatar bot">A</div>
      <div className="msg-body">
        <div className="msg-name">AskData</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, maxWidth: 480 }}>
          <p style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-primary)' }}>Доступные команды</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div style={{ display: 'flex', gap: 12, padding: '8px 12px', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 6 }}>
              <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 12, flexShrink: 0 }}>/data</code>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Показать доступные таблицы и описание данных</span>
            </div>
            <div style={{ display: 'flex', gap: 12, padding: '8px 12px', background: 'var(--bg-elevated)', border: '1px solid var(--border-default)', borderRadius: 6 }}>
              <code style={{ color: 'var(--accent)', fontFamily: 'var(--font-mono)', fontSize: 12, flexShrink: 0 }}>/help</code>
              <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>Показать список команд</span>
            </div>
          </div>
          <p style={{ fontSize: 11, color: 'var(--text-muted)' }}>
            Или задайте вопрос на русском: «Топ 5 городов по выручке за месяц»
          </p>
        </div>
      </div>
    </div>
  )
}
