import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { EmptyState, ErrorNotice, LoadingState, PageHeader, Panel, StatusPill } from '../components/UI.jsx'
import { formatDate } from '../components/format.js'

const pageSize = 20

export default function ProductCatalog() {
  const [categories, setCategories] = useState([])
  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [status, setStatus] = useState('')
  const [offset, setOffset] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let active = true
    api.categories().then((rows) => { if (active) setCategories(rows) }).catch((cause) => { if (active) setError(cause) })
    return () => { active = false }
  }, [])

  useEffect(() => {
    let active = true
    api.products({
      search: query,
      category_id: categoryId,
      status,
      limit: String(pageSize),
      offset: String(offset),
    }).then((result) => {
      if (active) {
        setItems(result.items)
        setTotal(result.total)
        setError(null)
      }
    }).catch((cause) => { if (active) setError(cause) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [query, categoryId, status, offset, reload])

  function applyFilters(event) {
    event.preventDefault()
    setLoading(true)
    setOffset(0)
    setQuery(search.trim())
  }

  return (
    <>
      <PageHeader eyebrow="MERCHANDISING" title="Product catalog" description="Search real catalog records and inspect category and availability state." />
      <ErrorNotice error={error} onRetry={() => setReload((value) => value + 1)} />
      <Panel className="catalog-panel">
        <form className="filter-toolbar" onSubmit={applyFilters}>
          <label className="search-field"><span className="sr-only">Search products</span><span aria-hidden="true">⌕</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search name, brand, or product ID" /></label>
          <label><span className="sr-only">Filter by category</span><select value={categoryId} onChange={(event) => { setLoading(true); setCategoryId(event.target.value); setOffset(0) }}><option value="">All categories</option>{categories.map((category) => <option value={category._id} key={category._id}>{category.name}</option>)}</select></label>
          <label><span className="sr-only">Filter by availability</span><select value={status} onChange={(event) => { setLoading(true); setStatus(event.target.value); setOffset(0) }}><option value="">All availability</option><option value="active">Active</option><option value="unavailable">Unavailable</option><option value="discontinued">Discontinued</option></select></label>
          <button className="button button-primary" type="submit">Search</button>
        </form>
        <div className="table-caption"><span>{loading ? 'Loading catalog…' : `${total.toLocaleString()} matching products`}</span><button className="text-button" onClick={() => { setLoading(true); setReload((value) => value + 1) }}>Refresh</button></div>
        {loading ? <LoadingState label="Loading products" /> : items.length ? (
          <>
            <div className="product-table-wrap">
              <table className="data-table product-table">
                <thead><tr><th>Product</th><th>Category</th><th>Price</th><th>Availability</th><th>Lifecycle</th></tr></thead>
                <tbody>{items.map((product) => (
                  <tr key={product._id}>
                    <td><div className="product-name"><span className="product-avatar">{product.name?.slice(0, 1) || 'P'}</span><div><strong>{product.name}</strong><small>{product._id}{product.brand ? ` · ${product.brand}` : ''}</small></div></div></td>
                    <td>{product.category?.name || <span className="muted">Missing category</span>}</td>
                    <td>{product.currency} {product.price}</td>
                    <td><StatusPill status={product.status} /></td>
                    <td><span className="availability-date">From {formatDate(product.available_from)}</span><span className="availability-date">To {product.available_to ? formatDate(product.available_to) : 'Open ended'}</span></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
            <div className="pagination"><span>Showing {offset + 1}–{Math.min(offset + items.length, total)} of {total}</span><div><button className="button button-outline button-small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>Previous</button><button className="button button-outline button-small" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>Next</button></div></div>
          </>
        ) : error ? <div className="state-box">Catalog records could not be loaded.</div> : <EmptyState title="No products found" description="Try a different search term or remove one of the catalog filters." />}
      </Panel>
    </>
  )
}
