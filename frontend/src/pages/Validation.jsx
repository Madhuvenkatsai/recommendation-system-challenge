import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorNotice, InlineError, LoadingState, MetricCard, PageHeader, Panel, StatusPill } from '../components/UI.jsx'
import { formatDate, formatNumber } from '../components/format.js'

const pageSize = 25

export default function Validation() {
  const [summary, setSummary] = useState(null)
  const [issues, setIssues] = useState([])
  const [total, setTotal] = useState(0)
  const [severity, setSeverity] = useState('')
  const [issueType, setIssueType] = useState('')
  const [offset, setOffset] = useState(0)
  const [job, setJob] = useState(null)
  const [loading, setLoading] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    api.validationSummary().then(async (report) => {
      const result = await api.validationIssues({
        generation_run_id: report.generation_run_id,
        severity,
        issue_type: issueType,
        limit: String(pageSize),
        offset: String(offset),
      })
      if (active) {
        setSummary(report)
        setIssues(result.items)
        setTotal(result.total)
        setError(null)
      }
    }).catch((cause) => { if (active) setError(cause) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [severity, issueType, offset, reload])

  useEffect(() => {
    if (!job?._id || !['queued', 'running'].includes(job.status)) return undefined
    const timer = window.setInterval(() => {
      api.validationJob(job._id)
        .then((next) => {
          setJob(next)
          if (next.status === 'completed') setReload((value) => value + 1)
        })
        .catch(setError)
    }, 1700)
    return () => window.clearInterval(timer)
  }, [job?._id, job?.status])

  async function runValidation() {
    setRunning(true)
    setError(null)
    try {
      setJob(await api.startValidation())
    } catch (cause) {
      setError(cause)
    } finally {
      setRunning(false)
    }
  }

  const completed = summary?.status === 'completed'
  return (
    <>
      <PageHeader eyebrow="DATA QUALITY" title="Validation" description="Inspect validation findings and their record-level traceability." action={<button className="button button-primary" onClick={runValidation} disabled={running || ['queued', 'running'].includes(job?.status)}>{running || ['queued', 'running'].includes(job?.status) ? 'Validation running…' : 'Run validation'}</button>} />
      <ErrorNotice error={error} />
      {job?.status === 'running' && <div className="notice notice-info" role="status"><span className="spinner" /><p>Validation is running. {formatNumber(job.issues_written || 0)} issue records written so far; full scan progress is not estimated.</p></div>}
      {job?.status === 'failed' && <InlineError error={job.error} />}
      {loading && !summary ? <LoadingState label="Loading validation results" /> : (
        <>
          <div className="validation-summary-line"><div><StatusPill status={summary?.status} /><span>{summary?.generation_run_id ? `Dataset ${summary.generation_run_id}` : summary?.detail}</span></div>{completed && <span>Validated {formatDate(summary.validated_at)}</span>}</div>
          {completed ? (
            <>
              <div className="metric-grid validation-metrics">
                <MetricCard label="Issues detected" value={formatNumber(summary.issue_count)} icon="validation" tone="red" note="Persisted findings for this dataset" />
                <MetricCard label="Clean records" value={formatNumber(summary.clean_record_count)} icon="catalog" tone="green" note="Core records scanned" />
                <MetricCard label="Anomalous fixture records" value={formatNumber(summary.anomalous_record_count)} icon="generation" tone="amber" note="Separate from baseline data" />
              </div>
              <div className="dashboard-grid">
                <Panel title="Issues by severity" subtitle="Counts from the validation summary">
                  <div className="bar-list">{Object.entries(summary.counts_by_severity || {}).map(([name, count]) => {
                    const max = Math.max(1, ...Object.values(summary.counts_by_severity || {}))
                    return <div className="bar-row" key={name}><span className="severity-name"><i className={`severity-dot ${name}`} />{name}</span><div className="bar-track"><i className={`bar-${name}`} style={{ width: `${(count / max) * 100}%` }} /></div><b>{formatNumber(count)}</b></div>
                  })}{!Object.keys(summary.counts_by_severity || {}).length && <p className="muted">No issue counts were returned.</p>}</div>
                </Panel>
                <Panel title="Issues by type" subtitle="Choose a type to filter issue details">
                  <div className="bar-list">{Object.entries(summary.counts_by_issue_type || {}).map(([name, count]) => {
                    const max = Math.max(1, ...Object.values(summary.counts_by_issue_type || {}))
                    return <button className="bar-row bar-filter-button" key={name} onClick={() => { setIssueType(issueType === name ? '' : name); setOffset(0) }}><span>{name.replaceAll('_', ' ')}</span><span className="bar-track"><i style={{ width: `${(count / max) * 100}%` }} /></span><b>{formatNumber(count)}</b></button>
                  })}{!Object.keys(summary.counts_by_issue_type || {}).length && <p className="muted">No issue types were reported.</p>}</div>
                </Panel>
              </div>
              <Panel title="Issue details" subtitle={`${formatNumber(total)} records match the selected filters`}>
                <div className="filter-toolbar validation-filters">
                  <label><span className="sr-only">Filter by severity</span><select value={severity} onChange={(event) => { setSeverity(event.target.value); setOffset(0) }}><option value="">All severities</option>{['critical', 'error', 'warning', 'info'].map((value) => <option key={value}>{value}</option>)}</select></label>
                  <label><span className="sr-only">Filter by issue type</span><select value={issueType} onChange={(event) => { setIssueType(event.target.value); setOffset(0) }}><option value="">All issue types</option>{Object.keys(summary.counts_by_issue_type || {}).map((value) => <option value={value} key={value}>{value.replaceAll('_', ' ')}</option>)}</select></label>
                </div>
                {loading ? <LoadingState label="Loading issue details" /> : issues.length ? (
                  <>
                    <div className="issue-list">{issues.map((issue) => (
                      <article className="issue-card" key={issue.issue_id}>
                        <div className="issue-main"><div className="issue-title"><StatusPill status={issue.severity} /><strong>{issue.issue_type.replaceAll('_', ' ')}</strong></div><p>{issue.description}</p><div className="issue-facts"><span>{issue.entity_type}: <b>{issue.entity_id || '—'}</b></span><span>Detected {formatDate(issue.detected_at)}</span></div></div>
                        <div className="traceability"><small>Generation run</small><code>{issue.generation_run_id}</code><small>Source records</small><div>{(issue.source_record_ids || []).map((id) => <code key={id}>{id}</code>)}</div><small>Ground-truth label</small><span>{issue.ground_truth_label}</span></div>
                      </article>
                    ))}</div>
                    <div className="pagination"><span>Showing {offset + 1}–{Math.min(offset + issues.length, total)} of {total}</span><div><button className="button button-outline button-small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button><button className="button button-outline button-small" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Next</button></div></div>
                  </>
                ) : <EmptyState title="No validation issues" description={issueType || severity ? 'No records match the selected filters.' : 'No issues were returned for this completed validation.'} />}
              </Panel>
            </>
          ) : (
            <Panel>{summary?.status === 'not_run' ? <EmptyState title="Validation has not run" description={summary.detail || 'Run validation against the latest completed dataset to populate this page.'} action={<button className="button button-primary button-small" onClick={runValidation} disabled={running}>Run validation</button>} /> : <EmptyState title="Validation summary unavailable" description={summary?.detail || 'Generate a dataset and connect MongoDB before viewing validation.'} />}</Panel>
          )}
        </>
      )}
    </>
  )
}
