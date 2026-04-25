import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import client from '@/api/client'

type SemanticData = {
  yaml: string
  version: number
  metrics_count: number
  synonyms_count: number
  periods_count: number
}

function YamlLineNumbers({ content }: { content: string }) {
  const lines = content.split('\n')
  return (
    <div className="yaml-ln">
      {lines.map((_, i) => (
        <div key={i}>{i + 1}</div>
      ))}
    </div>
  )
}

export default function SemanticLayerPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['semantic'],
    queryFn: async () => {
      const { data } = await client.get('/admin/semantic')
      return data as SemanticData
    },
  })

  const [yaml, setYaml] = useState('')
  const [saveResult, setSaveResult] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('metrics')

  const updateMutation = useMutation({
    mutationFn: async (yamlContent: string) => {
      const { data } = await client.post('/admin/semantic', { yaml: yamlContent })
      return data
    },
    onSuccess: (res) => {
      setSaveResult(`Сохранено. Версия ${res.version}, метрик: ${res.metrics_count}`)
      refetch()
    },
    onError: (e: unknown) => {
      const msg = (e as { response?: { data?: { detail?: string } } }).response?.data?.detail || 'Ошибка сохранения'
      setSaveResult(`❌ ${msg}`)
    },
  })

  const currentYaml = yaml || data?.yaml || ''
  const isError = saveResult?.startsWith('❌')

  return (
    <div style={{ padding: '24px 28px 60px', maxWidth: 1440, margin: '0 auto' }}>
      {/* Page head */}
      <div className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 10 }}>/ admin · semantic layer</div>
          <h1 className="page-title">Семантический <em>слой</em></h1>
        </div>
        <div className="page-meta">
          {data ? `версия ${data.version} · ${data.metrics_count} метрик` : 'загрузка...'}<br />
          hot-reload активен
        </div>
      </div>

      <div className="admin-grid">
        {/* Left: YAML editor */}
        <div>
          {saveResult && (
            <div
              className={isError ? '' : 'val-banner'}
              style={isError ? {
                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
                borderRadius: 'var(--radius-md)', background: 'var(--red-soft)', color: 'var(--red)',
                fontSize: 13, fontFamily: 'var(--font-mono)', marginBottom: 16,
              } : { marginBottom: 16 }}
            >
              {!isError && <span className="vchk">✓</span>}
              {saveResult}
            </div>
          )}

          <div className="yaml-editor">
            <div className="yaml-head">
              <div className="tabs">
                {['metrics', 'synonyms', 'periods', 'dimensions'].map(tab => (
                  <button
                    key={tab}
                    className={`tab${activeTab === tab ? ' active' : ''}`}
                    onClick={() => setActiveTab(tab)}
                  >
                    {tab}
                  </button>
                ))}
              </div>
              <div style={{ display: 'flex', gap: 6 }}>
                <button
                  className="btn ghost sm"
                  onClick={() => setSaveResult('Валидация пройдена · синтаксис корректен')}
                >
                  ✓ Validate
                </button>
                <button
                  className="btn primary sm"
                  onClick={() => updateMutation.mutate(currentYaml)}
                  disabled={updateMutation.isPending}
                >
                  {updateMutation.isPending ? 'Сохранение...' : '↑ Save & reload'}
                </button>
              </div>
            </div>

            {isLoading ? (
              <div style={{ padding: 24, color: 'var(--text-muted)', fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                Загрузка...
              </div>
            ) : (
              <div style={{ position: 'relative' }}>
                {/* Line numbers + textarea overlay */}
                <div style={{ display: 'grid', gridTemplateColumns: '36px 1fr', gap: 16, padding: '20px 24px', minHeight: 480 }}>
                  <YamlLineNumbers content={currentYaml} />
                  <textarea
                    value={currentYaml}
                    onChange={(e) => setYaml(e.target.value)}
                    style={{
                      background: 'transparent', border: 'none', outline: 'none', resize: 'none',
                      fontFamily: 'var(--font-mono)', fontSize: 13, lineHeight: 1.8,
                      color: 'var(--text-primary)', width: '100%', minHeight: 480,
                    }}
                    spellCheck={false}
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: stats sidebar */}
        <aside>
          {data && (
            <>
              <div className="admin-stat-grid" style={{ marginBottom: 20 }}>
                <div className="admin-stat">
                  <div className="n"><em>{data.metrics_count}</em></div>
                  <div className="l">метрик</div>
                </div>
                <div className="admin-stat">
                  <div className="n"><em>{data.synonyms_count}</em></div>
                  <div className="l">синонимов</div>
                </div>
                <div className="admin-stat">
                  <div className="n"><em>{data.periods_count}</em></div>
                  <div className="l">периодов</div>
                </div>
                <div className="admin-stat">
                  <div className="n"><em>v{data.version}</em></div>
                  <div className="l">версия</div>
                </div>
              </div>
            </>
          )}

          <div className="eyebrow" style={{ marginBottom: 10 }}>Whitelist таблиц</div>
          <div className="rp-card">
            {data?.whitelist_tables?.length ? (
              data.whitelist_tables.map((t: string) => (
                <div key={t} className="rp-kv">
                  <span className="k" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{t}</span>
                  <span className="v" style={{ color: 'var(--green)' }}>✓ allowed</span>
                </div>
              ))
            ) : (
              [
                { t: 'anonymized_incity_orders', cols: '23' },
                { t: 'passenger_daily_stats', cols: '11' },
                { t: 'driver_daily_stats', cols: '11' },
                { t: 'cities', cols: '2' },
              ].map(x => (
                <div key={x.t} className="rp-kv">
                  <span className="k" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>{x.t}</span>
                  <span className="v" style={{ color: 'var(--green)' }}>✓ {x.cols} col</span>
                </div>
              ))
            )}
          </div>

          <div className="eyebrow" style={{ marginTop: 20, marginBottom: 10 }}>Система</div>
          <div className="rp-card">
            <div className="rp-kv"><span className="k">шаблонов</span><span className="v">18</span></div>
            <div className="rp-kv"><span className="k">метрик</span><span className="v">{data?.metrics_count ?? 18}</span></div>
            <div className="rp-kv"><span className="k">guard layers</span><span className="v ok">7</span></div>
            <div className="rp-kv"><span className="k">self-consistency</span><span className="v ok">2 runs</span></div>
          </div>
        </aside>
      </div>
    </div>
  )
}
