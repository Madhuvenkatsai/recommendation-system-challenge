import { useState } from 'react'
import { API_BASE_URL } from './api.js'
import Icon from './components/Icon.jsx'
import { StatusPill } from './components/UI.jsx'
import Dashboard from './pages/Dashboard.jsx'
import DataGeneration from './pages/DataGeneration.jsx'
import Evaluation from './pages/Evaluation.jsx'
import ProductCatalog from './pages/ProductCatalog.jsx'
import RecommendationExplorer from './pages/RecommendationExplorer.jsx'
import Validation from './pages/Validation.jsx'
import './App.css'

const navigation = [
  { id: 'dashboard', label: 'Dashboard', icon: 'overview', group: 'Workspace' },
  { id: 'generation', label: 'Data generation', icon: 'generation', group: 'Workspace' },
  { id: 'catalog', label: 'Product catalog', icon: 'catalog', group: 'Workspace' },
  { id: 'recommendations', label: 'Recommendation explorer', icon: 'recommend', group: 'Models' },
  { id: 'validation', label: 'Validation', icon: 'validation', group: 'Models' },
  { id: 'evaluation', label: 'Evaluation', icon: 'evaluation', group: 'Models' },
]

const pageComponents = {
  dashboard: Dashboard,
  generation: DataGeneration,
  catalog: ProductCatalog,
  recommendations: RecommendationExplorer,
  validation: Validation,
  evaluation: Evaluation,
}

function App() {
  const initialPage = window.location.hash.slice(1)
  const [activePage, setActivePage] = useState(pageComponents[initialPage] ? initialPage : 'dashboard')
  const [databaseStatus, setDatabaseStatus] = useState('unknown')
  const ActivePage = pageComponents[activePage]

  function navigate(page) {
    setActivePage(page)
    window.history.replaceState(null, '', page === 'dashboard' ? '/' : `#${page}`)
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand-lockup" href="#" onClick={(event) => { event.preventDefault(); navigate('dashboard') }}>
          <span className="brand-mark">R</span>
          <span><b>Recsys</b><small>Commerce intelligence</small></span>
        </a>
        <nav className="side-navigation" aria-label="Main navigation">
          {['Workspace', 'Models'].map((group) => (
            <div className="nav-group" key={group}>
              <span className="nav-group-label">{group}</span>
              {navigation.filter((item) => item.group === group).map((item) => (
                <button
                  type="button"
                  className={`nav-link ${activePage === item.id ? 'active' : ''}`}
                  key={item.id}
                  aria-current={activePage === item.id ? 'page' : undefined}
                  onClick={() => navigate(item.id)}
                >
                  <Icon name={item.icon} size={18} />
                  <span>{item.label}</span>
                  {activePage === item.id && <Icon name="chevron" size={15} className="nav-chevron" />}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="sidebar-status">
            <span className={`connection-indicator ${databaseStatus === 'connected' ? 'is-connected' : ''}`} />
            <div><b>MongoDB</b><small>{databaseStatus === 'connected' ? 'Connected' : databaseStatus === 'unavailable' ? 'Unavailable' : 'Status from dashboard'}</small></div>
            <StatusPill status={databaseStatus} />
          </div>
          <p>Recommendation platform<br />Local development workspace</p>
        </div>
      </aside>
      <div className="main-column">
        <header className="topbar">
          <div className="breadcrumb"><span>Product Recommendation System</span><Icon name="chevron" size={14} /><b>{navigation.find((item) => item.id === activePage)?.label}</b></div>
          <div className="topbar-right">
            <span className="api-endpoint" title={API_BASE_URL}>API <code>{API_BASE_URL.replace(/^https?:\/\//, '')}</code></span>
            <span className="environment-tag">LOCAL</span>
          </div>
        </header>
        <nav className="mobile-navigation" aria-label="Mobile navigation">
          {navigation.map((item) => (
            <button type="button" className={activePage === item.id ? 'active' : ''} key={item.id} onClick={() => navigate(item.id)} aria-current={activePage === item.id ? 'page' : undefined}>
              <Icon name={item.icon} size={17} /><span>{item.label}</span>
            </button>
          ))}
        </nav>
        <main className="main-content">
          <ActivePage onNavigate={navigate} onConnection={setDatabaseStatus} />
        </main>
        <footer className="app-footer"><span>Recommendation Studio</span><span>Seeded synthetic data · 20261022</span></footer>
      </div>
    </div>
  )
}

export default App
