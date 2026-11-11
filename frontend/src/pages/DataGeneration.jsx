import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { ErrorNotice, LoadingState, PageHeader, Panel, StatusPill } from '../components/UI.jsx'
import { formatDate, formatNumber } from '../components/format.js'

export default function DataGeneration() {
  const [scale, setScale] = useState('starter')
  const [generationConfig, setGenerationConfig] = useState(null)
  const [injectAnomalies, setInjectAnomalies] = useState(false)
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let active = true
    Promise.all([api.generationStatus(), api.generationConfigurations()])
      .then(([data, configuration]) => {
        if (active) {
          setJob(data)
          setGenerationConfig(configuration)
          setError(null)
        }
      })
      .catch((cause) => { if (active) setError(cause) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (!job?._id || !['queued', 'running'].includes(job.status)) return undefined
    const timer = window.setInterval(() => {
      api.generationJob(job._id)
        .then(setJob)
        .catch(setError)
    }, 1800)
    return () => window.clearInterval(timer)
  }, [job?._id, job?.status])

  async function submit(event) {
    event.preventDefault()
    setBusy(true)
    setError(null)
    try {
      const created = await api.startGeneration({
        scale,
        seed: generationConfig.seed,
        batch_size: generationConfig.default_batch_size,
        inject_anomalies: injectAnomalies,
      })
      setJob(created)
    } catch (cause) {
      setError(cause)
    } finally {
      setBusy(false)
    }
  }

  const isRunning = ['queued', 'running'].includes(job?.status)
  const selectedScale = generationConfig?.scales.find((item) => item.value === scale)
  const expected = selectedScale?.configuration
  return (
    <>
      <PageHeader eyebrow="DATA PIPELINE" title="Data generation" description="Configure and run the deterministic synthetic dataset generator." />
      <ErrorNotice error={error} />
      <div className="two-column-layout generation-layout">
        <Panel title="Generation configuration" subtitle="The seed is fixed by the challenge for reproducible output.">
          <form className="form-stack" onSubmit={submit}>
            <label className="field-label" htmlFor="scale-select">Dataset scale</label>
            <select id="scale-select" value={scale} onChange={(event) => setScale(event.target.value)} disabled={busy || isRunning || !generationConfig}>
              {(generationConfig?.scales || []).map((item) => <option value={item.value} key={item.value}>{item.label} · {item.value === 'starter' ? 'fast development dataset' : 'challenge target volumes'}</option>)}
            </select>
            <label className="field-label" htmlFor="seed-value">Generation seed</label>
            <input id="seed-value" value={generationConfig?.seed ?? ''} readOnly aria-describedby="seed-note" />
            <span className="field-hint" id="seed-note">Fixed seed; it cannot be changed through the dashboard.</span>
            <label className="toggle-row">
              <input type="checkbox" checked={injectAnomalies} onChange={(event) => setInjectAnomalies(event.target.checked)} disabled={busy || isRunning} />
              <span><b>Include controlled anomaly fixtures</b><small>Clean baseline entities remain separate. Anomalies are opt-in.</small></span>
            </label>
            <div className="volume-preview">
              <p>Expected parent entity counts <span>from selected configuration</span></p>
              <div>{expected && ['customers', 'products', 'sessions', 'orders'].map((name) => <span key={name}><b>{formatNumber(expected[name])}</b>{name}</span>)}</div>
            </div>
            <button className="button button-primary" type="submit" disabled={busy || isRunning || loading || !generationConfig}>
              {busy || isRunning ? 'Generation in progress…' : 'Start generation'}
            </button>
            <p className="form-footnote">The API will not overwrite existing collection data. A fresh, initialized MongoDB database is required.</p>
          </form>
        </Panel>
        <Panel title="Run progress" subtitle="Progress is reported by the backend operation, not estimated.">
          {loading ? <LoadingState label="Checking generation status" /> : job && job.status !== 'not_started' ? (
            <div className="job-panel">
              <div className="job-status-line"><StatusPill status={job.status} /><span>{formatDate(job.updated_at || job.created_at)}</span></div>
              <code>{job._id}</code>
              {job.configuration && <div className="job-facts"><span>Scale <b>{job.configuration.scale}</b></span><span>Seed <b>{formatNumber(job.configuration.seed)}</b></span></div>}
              {isRunning && <div className="progress-state"><span className="spinner" /><div><b>{job.current_collection ? `Writing ${job.current_collection.replaceAll('_', ' ')}` : 'Preparing generation'}</b><p>{formatNumber(job.records_processed || 0)} records written so far. No percentage is estimated.</p></div></div>}
              {job.status === 'completed' && <div className="result-state"><strong>Generation complete</strong><p>Dataset {job.result?.dataset_version} completed at {formatDate(job.result?.completed_at)}.</p><div className="result-counts">{['customers', 'products', 'sessions', 'orders'].map((key) => <span key={key}>{key}<b>{formatNumber(job.result?.collection_counts?.[key])}</b></span>)}</div></div>}
              {job.status === 'failed' && <div className="inline-error">{job.error}</div>}
            </div>
          ) : (
            <div className="empty-state compact-empty"><span className="empty-mark">1</span><strong>Ready to generate</strong><p>No generation job has been started in this API process.</p></div>
          )}
        </Panel>
      </div>
      <div className="notice notice-info"><strong>Operational note</strong><p>Job state is held in the running API process. If the process restarts, pollable job history is lost; persisted completed runs remain in MongoDB.</p></div>
    </>
  )
}
