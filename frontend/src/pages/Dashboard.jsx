import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorNotice, LoadingState, MetricCard, PageHeader, Panel, StatusPill } from '../components/UI.jsx'
import { formatDate, formatNumber, percent } from '../components/format.js'

const collectionCards = [
  ['customers', 'Customers', 'overview', 'blue'],
  ['products', 'Products', 'catalog', 'violet'],
  ['sessions', 'Sessions', 'recommend', 'amber'],
  ['orders', 'Orders', 'evaluation', 'green'],
]

export default function Dashboard({ onNavigate, onConnection }) {
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const refresh = useCallback(() => setReload((value) => value + 1), [])

  useEffect(() => {
    let active = true
    api.overview()
      .then((data) => { if (active) { setOverview(data); setError(null); onConnection?.(data.database?.status || 'unknown') } })
      .catch((cause) => { if (active) { setError(cause); onConnection?.('unavailable') } })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reload, onConnection])

  const evaluationRows = (overview?.latest_evaluations || []).slice(0, 3)
  return (
    <>
      <PageHeader
        eyebrow="SYSTEM OVERVIEW"
        title="Dashboard"
        description="A live view of your generated dataset, data quality, and recommendation models."
        action={<button className="button button-outline" onClick={refresh} disabled={loading}><span className="button-icon">↻</span>Refresh</button>}
      />
      <ErrorNotice error={error} onRetry={refresh} />
      {loading && !overview ? <LoadingState label="Connecting to the API" /> : (
        <>
          <div className="connection-banner">
            <div className="connection-copy">
              <span className={`connection-indicator ${overview?.database?.status === 'connected' ? 'is-connected' : ''}`} />
              <div><strong>{overview?.database?.status === 'connected' ? 'MongoDB connected' : 'Database status unavailable'}</strong><p>{overview?.database?.name || 'Connect the backend to MongoDB to load project data.'}</p></div>
            </div>
            <StatusPill status={overview?.database?.status || (error ? 'unavailable' : 'unknown')} label={overview?.database?.status || (error ? 'unavailable' : 'unknown')} />
          </div>

          <div className="metric-grid">
            {collectionCards.map(([key, label, icon, tone]) => (
              <MetricCard key={key} label={`Total ${label.toLowerCase()}`} value={formatNumber(overview?.counts?.[key])} icon={icon} tone={tone} note="Current database count" />
            ))}
          </div>

          <div className="dashboard-grid">
            <Panel title="Dataset generation" subtitle="Most recent persisted generation run" action={<button className="text-button" onClick={() => onNavigate('generation')}>Open generation <span>→</span></button>}>
              {overview?.generation?.latest_run ? (
                <div className="workflow-content">
                  <div className="workflow-top"><StatusPill status={overview.generation.status} /><span className="muted">{formatDate(overview.generation.latest_run.completed_at)}</span></div>
                  <div className="run-id">{overview.generation.latest_run._id}</div>
                  <div className="run-facts"><span>Customers <b>{formatNumber(overview.generation.latest_run.configuration?.customers)}</b></span><span>Products <b>{formatNumber(overview.generation.latest_run.configuration?.products)}</b></span><span>Seed <b>{formatNumber(overview.generation.latest_run.seed)}</b></span></div>
                  <p className="small-note">Counts reflect the latest run manifest; cards above show current collection totals.</p>
                </div>
              ) : (
                <EmptyState title="No generation run yet" description="Start a starter or full dataset run to populate MongoDB." action={<button className="button button-primary button-small" onClick={() => onNavigate('generation')}>Configure generation</button>} />
              )}
            </Panel>

            <Panel title="Validation status" subtitle="Latest dataset validation summary" action={<button className="text-button" onClick={() => onNavigate('validation')}>View validation <span>→</span></button>}>
              <div className="validation-overview">
                <div className="validation-number">{overview?.validation?.issue_count === null || overview?.validation?.issue_count === undefined ? '—' : formatNumber(overview.validation.issue_count)}<span>issues</span></div>
                <StatusPill status={overview?.validation?.status} />
              </div>
              <p className="small-note">{overview?.validation?.detail || 'Validation has not been run.'}</p>
              {overview?.validation?.counts_by_severity && Object.keys(overview.validation.counts_by_severity).length > 0 && (
                <div className="severity-list">
                  {Object.entries(overview.validation.counts_by_severity).map(([severity, count]) => <div key={severity}><span className={`severity-dot ${severity}`} />{severity}<b>{formatNumber(count)}</b></div>)}
                </div>
              )}
            </Panel>

            <Panel title="Recommendation strategies" subtitle="Configured model approaches" action={<button className="text-button" onClick={() => onNavigate('recommendations')}>Explore <span>→</span></button>}>
              <div className="strategy-list">
                {Object.entries(overview?.recommendations?.strategies || {}).map(([name, strategy]) => (
                  <div className="strategy-row" key={name}><span className={`strategy-symbol ${name}`}>{name.slice(0, 1).toUpperCase()}</span><div><strong>{name[0].toUpperCase() + name.slice(1)}</strong><p>{strategy.description}</p></div></div>
                ))}
                {!overview?.recommendations && <p className="muted">Strategy information is unavailable.</p>}
              </div>
            </Panel>

            <Panel title="Latest evaluations" subtitle="Persisted test-split metrics" action={<button className="text-button" onClick={() => onNavigate('evaluation')}>Compare models <span>→</span></button>}>
              {evaluationRows.length ? (
                <div className="evaluation-mini-list">
                  {evaluationRows.map((row) => (
                    <div className="evaluation-mini" key={row._id}>
                      <div><strong>{row.strategy || 'Strategy unavailable'}</strong><span>K={row.k} · {formatNumber(row.sample_count)} users</span></div>
                      <div className="mini-metric"><b>{percent(row.metrics?.ndcg_at_k)}</b><span>NDCG</span></div>
                      <div className="mini-metric"><b>{percent(row.metrics?.precision_at_k)}</b><span>Precision</span></div>
                    </div>
                  ))}
                </div>
              ) : (
                <EmptyState title="No evaluation results" description="Run evaluation after a dataset has been generated and validated." action={<button className="button button-outline button-small" onClick={() => onNavigate('evaluation')}>Open evaluation</button>} />
              )}
            </Panel>

            {overview?.validation?.status === 'completed' && (
              <Panel title="Issue distribution" subtitle="Counts reported by the latest validation" className="wide-panel">
                <div className="bar-list">
                  {Object.entries(overview.validation.counts_by_issue_type || {}).map(([type, count]) => {
                    const max = Math.max(1, ...Object.values(overview.validation.counts_by_issue_type || {}))
                    return <div className="bar-row" key={type}><span>{type.replaceAll('_', ' ')}</span><div className="bar-track"><i style={{ width: `${(count / max) * 100}%` }} /></div><b>{formatNumber(count)}</b></div>
                  })}
                  {!Object.keys(overview.validation.counts_by_issue_type || {}).length && <p className="muted">The completed validation summary reported no issue types.</p>}
                </div>
              </Panel>
            )}
          </div>
        </>
      )}
    </>
  )
}
