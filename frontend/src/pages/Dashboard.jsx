import { useCallback, useEffect, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, Panel, StatusPill } from '../components/UI.jsx'
import { formatDate, formatNumber, percent } from '../components/format.js'

const coreEntities = [
  ['customers', 'Customers', 20_000],
  ['products', 'Products', 10_000],
  ['categories', 'Categories'],
  ['sessions', 'Sessions', 500_000],
  ['page_views', 'Page views'],
  ['carts', 'Carts'],
  ['cart_lines', 'Cart lines'],
  ['orders', 'Orders', 100_000],
  ['order_lines', 'Order lines'],
  ['product_relations', 'Product relations'],
  ['recommendations', 'Recommendations'],
]

const supportingCollections = [
  ['generation_runs', 'Generation runs'],
  ['lifecycle_events', 'Lifecycle events'],
  ['validation_issues', 'Validation issues'],
  ['anomaly_fixtures', 'Anomaly fixtures'],
  ['dataset_splits', 'Dataset splits'],
  ['ground_truth_labels', 'Ground-truth labels'],
  ['model_runs', 'Model runs'],
  ['evaluation_results', 'Evaluation results'],
]

function progressText(actual, target) {
  if (actual === null || actual === undefined || !target) return '—'
  return `${Number(((actual / target) * 100).toFixed(1))}%`
}

export default function Dashboard({ onNavigate, onConnection }) {
  const [overview, setOverview] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(true)
  const [reload, setReload] = useState(0)
  const refresh = useCallback(() => {
    setOverview(null)
    setError(null)
    setLoading(true)
    setReload((value) => value + 1)
  }, [])

  useEffect(() => {
    let active = true
    api.overview()
      .then((data) => { if (active) { setOverview(data); setError(null); onConnection?.(data.database?.status || 'unknown') } })
      .catch((cause) => { if (active) { setOverview(null); setError(cause); onConnection?.('unavailable') } })
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

          <div className="dashboard-grid">
            <Panel title="Core entity counts" subtitle="Live persisted MongoDB counts compared with the full-scale challenge targets." className="wide-panel">
              <div className="entity-count-grid">
                {coreEntities.map(([key, label, challengeTarget]) => {
                  const actual = overview?.counts?.[key]
                  const target = overview?.full_scale_targets?.[key] ?? challengeTarget
                  return (
                    <article className="entity-count-card" key={key}>
                      <span className="entity-count-label">{label}</span>
                      <strong className="entity-count-value">{formatNumber(actual)}</strong>
                      <span className="entity-count-target">
                        {target === undefined ? 'Full-scale target not specified' : `Full-scale target ${formatNumber(target)}`}
                      </span>
                      {target !== undefined && (
                        <div className="entity-progress" aria-label={`${label} progress ${progressText(actual, target)}`}>
                          <div className="entity-progress-track"><i style={{ width: `${actual === null || actual === undefined ? 0 : Math.min(100, (actual / target) * 100)}%` }} /></div>
                          <span>{progressText(actual, target)} of target</span>
                        </div>
                      )}
                    </article>
                  )
                })}
              </div>
            </Panel>

            <Panel title="Supporting collection counts" subtitle="Live counts for audit, validation, split, label, and evaluation collections." className="wide-panel">
              <div className="supporting-count-grid">
                {supportingCollections.map(([key, label]) => (
                  <div className="supporting-count-card" key={key}>
                    <span>{label}</span>
                    <strong>{formatNumber(overview?.counts?.[key])}</strong>
                  </div>
                ))}
              </div>
            </Panel>

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
