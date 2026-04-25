import { useState, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, Outlet, NavLink, useNavigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthStore } from '@/store/auth'
import LoginPage from '@/pages/Login'
import ChatPage from '@/pages/Chat'
import ReportsPage from '@/pages/Reports'
import ReportDetailPage from '@/pages/ReportDetail'
import SchedulesPage from '@/pages/Schedules'
import SemanticLayerPage from '@/pages/Admin/SemanticLayer'
import AuditLogPage from '@/pages/Admin/AuditLog'
import RagExamplesPage from '@/pages/Admin/RagExamples'
import DashboardsPage from '@/pages/Dashboards'
import DashboardDetailPage from '@/pages/DashboardDetail'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
})

function RequireAuth({ minRole }: { minRole?: 'viewer' | 'analyst' | 'admin' }) {
  const { user, isRole } = useAuthStore()
  if (!user) return <Navigate to="/login" replace />
  if (minRole && !isRole(minRole)) return <Navigate to="/reports" replace />
  return <Outlet />
}

const ROLE_COLORS: Record<string, string> = {
  analyst: 'var(--accent)',
  admin: '#BC8CFF',
  viewer: '#5B8CFF',
}

function TopNav() {
  const { user, isRole, clearAuth } = useAuthStore()
  const navigate = useNavigate()
  const [scrolled, setScrolled] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 80)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const navLinks = [
    ...(isRole('analyst') ? [{ to: '/chat', label: 'Chat' }] : []),
    { to: '/reports', label: 'Reports' },
    ...(isRole('analyst') ? [
      { to: '/dashboards', label: 'Dashboards' },
      { to: '/schedules', label: 'Schedules' },
    ] : []),
    ...(isRole('admin') ? [
      { to: '/admin/semantic', label: 'Semantic' },
      { to: '/admin/audit', label: 'Audit' },
      { to: '/admin/rag', label: 'RAG' },
    ] : []),
  ]

  const roleClass = user?.role === 'analyst' ? 'role-analyst' : user?.role === 'admin' ? 'role-admin' : 'role-viewer'
  const initials = user?.username?.slice(0, 2).toUpperCase() ?? '?'
  const avatarColor = user ? (ROLE_COLORS[user.role] ?? 'var(--accent)') : 'var(--accent)'
  const avatarTextColor = user?.role === 'analyst' ? 'var(--accent-text)' : '#fff'

  return (
    <>
      <header className="topbar">
        <NavLink to="/" className="brand" style={{ textDecoration: 'none', color: 'inherit' }}>
          <span className="brand-mark">a</span>
          <span className="brand-name">Ask<em>Data</em></span>
          <span className="brand-sub">/ Drivee NL→SQL</span>
        </NavLink>

        <nav className="nav">
          {navLinks.map(({ to, label }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) => isActive ? 'active' : ''}
            >
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="top-right">
          {user && (
            <div className="user-pill">
              <span
                className="avatar"
                style={{ background: avatarColor, color: avatarTextColor }}
              >
                {initials}
              </span>
              <span>{user.username}</span>
              <span className={`role-chip ${roleClass}`}>{user.role}</span>
              <button
                onClick={() => { clearAuth(); navigate('/login') }}
                className="btn ghost sm"
                style={{ padding: '2px 6px', marginLeft: 2 }}
                title="Выйти"
              >
                ×
              </button>
            </div>
          )}
        </div>
      </header>

      {/* Floating pill nav on scroll */}
      <nav className={`floating-nav${scrolled ? ' visible' : ''}`}>
        {navLinks.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => isActive ? 'active' : ''}
            style={{
              padding: '7px 14px', borderRadius: '999px', fontSize: 13, color: 'var(--text-secondary)',
              fontWeight: 500, display: 'inline-flex', alignItems: 'center', textDecoration: 'none',
            }}
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </>
  )
}

function AppLayout() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', minHeight: '100vh', background: 'var(--bg-base)' }}>
      <TopNav />
      <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Outlet />
      </main>
    </div>
  )
}

export default function App() {
  const { user } = useAuthStore()

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={user ? <Navigate to={user.role === 'viewer' ? '/reports' : '/chat'} replace /> : <LoginPage />} />

          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route element={<RequireAuth minRole="analyst" />}>
                <Route path="/chat" element={<ChatPage />} />
                <Route path="/schedules" element={<SchedulesPage />} />
              </Route>

              <Route path="/reports" element={<ReportsPage />} />
              <Route path="/reports/:id" element={<ReportDetailPage />} />

              <Route element={<RequireAuth minRole="analyst" />}>
                <Route path="/dashboards" element={<DashboardsPage />} />
                <Route path="/dashboards/:id" element={<DashboardDetailPage />} />
              </Route>

              <Route element={<RequireAuth minRole="admin" />}>
                <Route path="/admin/semantic" element={<SemanticLayerPage />} />
                <Route path="/admin/audit" element={<AuditLogPage />} />
                <Route path="/admin/whitelist" element={<SemanticLayerPage />} />
                <Route path="/admin/rag" element={<RagExamplesPage />} />
              </Route>
            </Route>
          </Route>

          <Route path="/" element={<Navigate to={user ? (user.role === 'viewer' ? '/reports' : '/chat') : '/login'} replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}
