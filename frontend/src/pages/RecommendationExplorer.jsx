import { useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, Panel, StatusPill } from '../components/UI.jsx'
import { formatDate } from '../components/format.js'

export default function RecommendationExplorer() {
  const [customerSearch, setCustomerSearch] = useState('')
  const [customers, setCustomers] = useState([])
  const [customerId, setCustomerId] = useState('')
  const [strategy, setStrategy] = useState('hybrid')
  const [k, setK] = useState(10)
  const [asOf, setAsOf] = useState('')
  const [recommendation, setRecommendation] = useState(null)
  const [searching, setSearching] = useState(false)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState(null)

  async function findCustomers(event) {
    event.preventDefault()
    setSearching(true)
    setError(null)
    try {
      const rows = await api.customers(customerSearch.trim())
      setCustomers(rows)
      setCustomerId(rows[0]?._id || '')
      setRecommendation(null)
    } catch (cause) {
      setError(cause)
    } finally {
      setSearching(false)
    }
  }

  async function generate(event) {
    event.preventDefault()
    if (!customerId) return
    setRunning(true)
    setError(null)
    try {
      const payload = { strategy, k: Number(k) }
      if (asOf) payload.as_of_time = new Date(asOf).toISOString()
      setRecommendation(await api.recommend(customerId, payload))
    } catch (cause) {
      setError(cause)
    } finally {
      setRunning(false)
    }
  }

  return (
    <>
      <PageHeader eyebrow="PERSONALIZATION" title="Recommendation explorer" description="Generate a traceable ranked list using the backend recommendation service." />
      <ErrorNotice error={error} />
      <div className="two-column-layout explorer-layout">
        <Panel title="Recommendation request" subtitle="Select a customer and strategy. Held-out labels are not available in this workflow.">
          <form className="form-stack" onSubmit={findCustomers}>
            <label className="field-label" htmlFor="customer-search">Find a customer</label>
            <div className="input-with-button"><input id="customer-search" value={customerSearch} onChange={(event) => setCustomerSearch(event.target.value)} placeholder="Enter customer ID or prefix" /><button className="button button-outline" disabled={searching} type="submit">{searching ? 'Searching…' : 'Find'}</button></div>
          </form>
          {customers.length > 0 && (
            <form className="form-stack recommendation-form" onSubmit={generate}>
              <label className="field-label" htmlFor="customer-choice">Customer</label>
              <select id="customer-choice" value={customerId} onChange={(event) => setCustomerId(event.target.value)}>{customers.map((customer) => <option key={customer._id} value={customer._id}>{customer._id}{customer.segment ? ` · ${customer.segment}` : ''}{customer.region ? ` · ${customer.region}` : ''}</option>)}</select>
              <label className="field-label" htmlFor="strategy-choice">Strategy</label>
              <select id="strategy-choice" value={strategy} onChange={(event) => setStrategy(event.target.value)}><option value="hybrid">Hybrid</option><option value="popularity">Popularity</option><option value="content">Content-based</option></select>
              <label className="field-label" htmlFor="top-k">Top K</label>
              <select id="top-k" value={k} onChange={(event) => setK(event.target.value)}>{[5, 10, 20, 50, 100].map((value) => <option key={value} value={value}>{value} products</option>)}</select>
              <label className="field-label" htmlFor="as-of-time">Recommendation time <span className="optional-label">optional</span></label>
              <input id="as-of-time" type="datetime-local" value={asOf} onChange={(event) => setAsOf(event.target.value)} />
              <span className="field-hint">When omitted, the API uses the current time. Product availability and purchase exclusions are evaluated by the backend at that time.</span>
              <button className="button button-primary" type="submit" disabled={running}>{running ? 'Generating…' : 'Generate recommendations'}</button>
            </form>
          )}
          {customers.length === 0 && !searching && <EmptyState title="Search for a customer" description="Customer choices come from the connected dataset; no sample customer is inserted." />}
        </Panel>

        <Panel title="Ranked recommendations" subtitle="Scores and explanations returned by the API">
          {running ? <LoadingState label="Scoring eligible catalog items" /> : recommendation ? (
            <div className="recommendation-results">
              <div className="recommendation-meta"><span><b>{recommendation.customer_id}</b> · {recommendation.strategy}</span><StatusPill status={recommendation.status} /></div>
              <div className="recommendation-meta muted"><span>As of {formatDate(recommendation.as_of_time)}</span><span>Model {recommendation.model_version}</span></div>
              <div className="notice notice-info compact-notice">Unavailable, discontinued-at-time, and previously completed-purchased products are filtered by the recommendation service. This API response does not return an excluded-item list.</div>
              {recommendation.items?.length ? recommendation.items.map((item) => (
                <article className="recommendation-item" key={item.product_id}>
                  <span className="rank-number">{String(item.rank).padStart(2, '0')}</span>
                  <div className="recommendation-item-main"><div><strong>{item.product_id}</strong><StatusPill status={item.eligibility_status} /></div><p>{item.reason || 'No explanation was provided.'}</p>{item.source_interaction_ids?.length > 0 && <small>Sources: {item.source_interaction_ids.join(', ')}</small>}</div>
                  <div className="score-box"><b>{Number(item.score).toFixed(3)}</b><span>score</span></div>
                </article>
              )) : <EmptyState title="No eligible recommendations" description="No products passed the current availability and purchase-exclusion rules." />}
            </div>
          ) : <EmptyState title="No recommendation generated" description="Choose a customer and submit a request to inspect its ranked products." />}
        </Panel>
      </div>
    </>
  )
}
