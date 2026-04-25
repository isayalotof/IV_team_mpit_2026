import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { login } from '@/api/auth'
import { useAuthStore } from '@/store/auth'

const DEMO_USERS = [
  {
    role: 'viewer' as const,
    username: 'viewer',
    password: 'viewer123',
    name: 'Полина В.',
    desc: 'читает публичные отчёты',
    roleLabel: 'Viewer',
    roleClass: 'role-viewer',
  },
  {
    role: 'analyst' as const,
    username: 'manager',
    password: 'manager123',
    name: 'Максим К.',
    desc: 'задаёт вопросы, строит отчёты',
    roleLabel: 'Analyst',
    roleClass: 'role-analyst',
  },
  {
    role: 'admin' as const,
    username: 'admin',
    password: 'admin123',
    name: 'Аня С.',
    desc: 'управляет словарём и whitelist',
    roleLabel: 'Admin',
    roleClass: 'role-admin',
  },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const handleLogin = async (u?: string, p?: string) => {
    const user = u ?? username
    const pass = p ?? password
    if (!user || !pass) {
      setError('Введите логин и пароль')
      return
    }
    setLoading(true)
    setError('')
    try {
      const data = await login(user, pass)
      setAuth(data.user, data.access_token)
      navigate(data.user.role === 'viewer' ? '/reports' : '/chat')
    } catch {
      setError('Неверный логин или пароль')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      {/* Left column */}
      <div className="login-left">
        <div>
          <div className="eyebrow" style={{ marginBottom: 20 }}>
            МПИТ · 25/26 · трек «Специалисты» · кейс Drivee
          </div>
          <h1>
            Спроси <em>данные</em><br />как коллегу.
          </h1>
          <p className="lede">
            Self-service аналитика на естественном русском. NL → SQL с валидацией,
            guardrails, семантическим слоем и автопересчётом.
            Шаблоны — мгновенно; LLM-путь — 5–10&nbsp;с с оценкой достоверности.
          </p>
        </div>
        <div className="kpis">
          <div className="kpi-b">
            <div className="n">18</div>
            <div className="l">шаблонов вопросов</div>
          </div>
          <div className="kpi-b">
            <div className="n">22</div>
            <div className="l">метрик в словаре</div>
          </div>
          <div className="kpi-b">
            <div className="n">7</div>
            <div className="l">слоёв защиты</div>
          </div>
          <div className="kpi-b">
            <div className="n">3</div>
            <div className="l">роли пользователей</div>
          </div>
        </div>
      </div>

      {/* Right column */}
      <div className="login-right">
        <div className="login-card">
          <h2>Вход</h2>

          <div className="field">
            <label>Логин</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
              placeholder="username"
              autoComplete="username"
            />
          </div>
          <div className="field">
            <label>Пароль</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleLogin()}
              placeholder="••••••••"
              autoComplete="current-password"
            />
          </div>

          {error && (
            <p style={{ color: 'var(--red)', fontSize: 12, fontFamily: 'var(--font-mono)', marginBottom: 10 }}>
              {error}
            </p>
          )}

          <button
            className="btn primary"
            style={{ width: '100%', justifyContent: 'center', padding: '11px 14px', fontSize: 14 }}
            onClick={() => handleLogin()}
            disabled={loading}
          >
            {loading ? 'Входим...' : 'Войти →'}
          </button>

          <div className="divider">или быстрый вход для демо</div>

          <div className="quick-login">
            {DEMO_USERS.map((u) => (
              <button
                key={u.username}
                className="ql"
                onClick={() => handleLogin(u.username, u.password)}
                disabled={loading}
              >
                <span className={`role-chip ${u.roleClass}`}>{u.roleLabel}</span>
                <span className="nm">{u.name}</span>
                <span className="ds">{u.desc}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
