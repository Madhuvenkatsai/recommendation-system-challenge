import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, Panel } from '../components/UI.jsx'
import { formatDate, formatNumber, percent } from '../components/format.js'

const metricDefinitions = [
  ['precision_at_k', 'Precision@K', 'Ranking precision among the top K results.'],
  ['recall_at_k', 'Recall@K', 'Share of eligible held-out purchases retrieved.'],
  ['ndcg_at_k', 'NDCG@K', 'Ranking quality with stronger weight for early hits.'],
  ['hit_rate_at_k', 'Hit Rate@K', 'Share of evaluable users with at least one hit.'],
  ['catalog_coverage', 'Catalog coverage', 'Share of eligible catalog items recommended.'],
  ['cold_start_coverage', 'Cold-start coverage', 'Coverage of eligible cold-start products.'],
]

const strategies = ['popularity', 'content', 'hybrid']

export default function Evaluation() {
  const [results, setResults] = useState([])
  const [kValues, setKValues] = useState([5, 10])
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    api.evaluations()
      .then((rows) => { if (active) { setResults(rows); setError(null) } })
      .catch((cause) => { if (active) setError(cause) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [reload])

  const byStrategy = useMemo(() => {
    const latest = new Map()
    for (const result of results) {
      const strategy = result.strategy
      if (!strategy) continue
      const key = `${strategy}:${result.k}`
      const existing = latest.get(key)
      if (!existing || new Date(result.evaluated_at) > new Date(existing.evaluated_at)) latest.set(key, result)
    }
    return latest
  }, [results])

  async function runEvaluation() {
    setRunning(true)
    setError(null)
    try {
      const generated = await api.runEvaluation(kValues)
      setResults((previous) => [...generated, ...previous])
      setReload((value) => value + 1)
    } catch (cause) {
      setError(cause)
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <PageHeader eyebrow="MODEL QUALITY" title="Evaluation" description="Compare strategy metrics calculated from eligible held-out test-period purchase labels." action={<button className="button button-primary" onClick={runEvaluation} disabled={running}>{running ? 'Evaluating…' : 'Run evaluation'}</button>} />
      <ErrorNotice error={error} />
      <Panel title="Evaluation configuration" subtitle="Test labels are used only for scoring, never as recommendation inputs.">
        <div className="evaluation-controls"><fieldset><legend>Cutoff values</legend>{[5, 10].map((value) =>         <label className="checkbox-option" key={value}><input type="checkbox" checked={kValues.includes(value)} disabled={kValues.length === 1 && kValues.includes(value)} onChange={(event) => setKValues((values) => event.target.checked ? [...values, value].sort((a, b) => a - b) : values.filter((item) => item !== value))} />K={value}</label>)}</fieldset><span className="muted">The API supports K values from 1 to 100. Choose one or both standard cutoffs.</span></div>
      </Panel>
      {loading && !results.length ? <LoadingState label="Loading persisted evaluation results" /> : results.length ? (
        <div className="evaluation-results">
          {kValues.map((k) => (
            <Panel key={k} title={`Metrics at K=${k}`} subtitle="Each strategy is scored independently on the same test split.">
              <div className="comparison-chart" aria-label={`Evaluation metrics comparison at K=${k}`}>
                <div className="comparison-chart-header"><span>Metric</span>{strategies.map((strategy) => <span key={strategy}>{strategy}</span>)}</div>
                {metricDefinitions.map(([key, label]) => (
                  <div className="comparison-chart-row" key={key}>
                    <span>{label}</span>
                    {strategies.map((strategy) => {
                      const value = byStrategy.get(`${strategy}:${k}`)?.metrics?.[key]
                      return (
                        <div className="comparison-chart-cell" key={strategy} aria-label={`${strategy} ${label}: ${percent(value)}`}>
                          <span className="comparison-track"><i className={`chart-${strategy}`} style={{ width: `${value == null ? 0 : Math.max(0, Math.min(1, value)) * 100}%` }} /></span>
                          <b>{percent(value)}</b>
                        </div>
                      )
                    })}
                  </div>
                ))}
              </div>
              <div className="strategy-metric-grid">
                {strategies.map((strategy) => {
                  const result = byStrategy.get(`${strategy}:${k}`)
                  return (
                    <section className="strategy-metric-card" key={strategy}>
                      <div className="strategy-card-heading"><span className={`strategy-symbol ${strategy}`}>{strategy.slice(0, 1).toUpperCase()}</span><div><h3>{strategy[0].toUpperCase() + strategy.slice(1)}</h3><span>{result ? `Evaluated ${formatDate(result.evaluated_at)}` : 'No result for this K'}</span></div></div>
                      {result ? (
                        <>
                          <div className="metric-value-grid">{metricDefinitions.map(([key, label]) => <div key={key}><span>{label}</span><b>{percent(result.metrics?.[key])}</b></div>)}</div>
                          <div className="evaluation-foot">
                            <span>{formatNumber(result.metrics?.evaluable_user_count)} evaluable · {formatNumber(result.metrics?.skipped_user_count)} skipped</span>
                            <span>{formatNumber(result.metrics?.test_label_count)} labels · Precision denominator {formatNumber(result.metrics?.precision_denominator)}</span>
                          </div>
                          {result.metrics?.evaluation_status === 'insufficient_test_data' && <p className="small-note">Insufficient eligible test relevance; metrics are intentionally unavailable.</p>}
                        </>
                      ) : <EmptyState title="No stored result" description="Run evaluation to create this strategy and cutoff result." />}
                    </section>
                  )
                })}
              </div>
            </Panel>
          ))}
          <Panel title="Metric interpretation" subtitle="Denominators and sample limitations reported by the backend">
            <div className="metric-definition-grid">{metricDefinitions.map(([, title, description]) => <div key={title}><strong>{title}</strong><p>{description}</p></div>)}</div>
            <p className="small-note">Users without eligible test-period ground-truth items are skipped. Precision, recall, NDCG, hit rate, catalog coverage, cold-start coverage, denominators, and skipped-user counts are returned by the API; null values are not treated as zeros.</p>
          </Panel>
        </div>
      ) : <Panel><EmptyState title="No evaluation results" description="Run evaluation after a completed generation run with a test split is available." action={<button className="button button-primary button-small" onClick={runEvaluation} disabled={running}>Run evaluation</button>} /></Panel>}
    </>
  )
}
