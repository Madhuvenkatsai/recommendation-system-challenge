import Icon from './Icon.jsx'

export function PageHeader({ eyebrow, title, description, action }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <p className="eyebrow">{eyebrow}</p>}
        <h1>{title}</h1>
        {description && <p className="page-description">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function Panel({ title, subtitle, action, children, className = '' }) {
  return (
    <section className={`panel ${className}`}>
      {(title || action) && (
        <div className="panel-heading">
          <div>
            {title && <h2>{title}</h2>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  )
}

export function MetricCard({ label, value, note, icon, tone = 'blue' }) {
  return (
    <article className="metric-card">
      <div className={`metric-icon ${tone}`}><Icon name={icon} size={19} /></div>
      <p>{label}</p>
      <strong>{value ?? '—'}</strong>
      {note && <span>{note}</span>}
    </article>
  )
}

export function StatusPill({ status, label }) {
  const normalized = String(status || 'unknown').toLowerCase().replaceAll('_', '-')
  return <span className={`status-pill status-${normalized}`}>{label || status || 'Unknown'}</span>
}

export function LoadingState({ label = 'Loading data' }) {
  return <div className="state-box" role="status"><span className="spinner" />{label}…</div>
}

export function ErrorNotice({ error, onRetry }) {
  if (!error) return null
  return (
    <div className="notice notice-error" role="alert">
      <div><strong>Unable to load this view</strong><p>{error.message || error}</p></div>
      {onRetry && <button className="button button-outline button-small" onClick={onRetry}>Retry</button>}
    </div>
  )
}

export function EmptyState({ title, description, action }) {
  return (
    <div className="empty-state">
      <span className="empty-mark"><Icon name="overview" size={20} /></span>
      <strong>{title}</strong>
      <p>{description}</p>
      {action}
    </div>
  )
}

export function InlineError({ error }) {
  if (!error) return null
  return <div className="inline-error" role="alert">{error.message || error}</div>
}
